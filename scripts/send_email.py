"""
配置驱动的邮件发送模块，推荐使用 QQ 邮箱 SMTP 服务。

使用方式
--------
CLI::

    python send_email.py --to foo@example.com --subject "标题" --body "正文"
    python send_email.py --to foo@example.com --subject "标题" --body-file body.txt --html

模块::

    from scripts.send_email import send_email

    send_email(
        to="foo@example.com",
        subject="标题",
        body="正文",
    )

异步批量发送::

    import asyncio
    from scripts.send_email import EmailTask, send_emails_async

    tasks = [
        EmailTask(to="foo@example.com", subject="标题1", body="正文1"),
        EmailTask(to="bar@example.com", subject="标题2", body="正文2", html=True),
    ]

    results = asyncio.run(send_emails_async(tasks))

    for r in results:
        if r.success:
            print(f"发送成功：{r.task.subject}")
        else:
            print(f"发送失败：{r.task.subject}，原因：{r.error}")

配置文件
--------
默认读取脚本同目录下的 email_config.json，也可通过 config_path 参数指定。
配置格式参见 email_config.example.json。

QQ 邮箱开启 SMTP
----------------
1. 登录 QQ 邮箱（mail.qq.com）→ 设置 → 账户
2. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务」
3. 开启「POP3/SMTP 服务」，按提示发送短信验证
4. 验证完成后获得授权码，将授权码填入 email_config.json 的 password 字段
   （注意：填写的是授权码，而非 QQ 账号的登录密码）
5. smtp_host=smtp.qq.com，smtp_port=465

发送限额
--------
为避免账号被封禁，模块内置以下限制：
- 每小时最多发送 10 封
- 每天最多发送 100 封
超出限额时发送将被拒绝并记录日志，统计数据持久化到脚本同目录的
email_rate_limit.json。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import smtplib
import socket
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage, Message
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

# 默认配置文件路径（脚本同目录下）
_DEFAULT_CONFIG = Path(__file__).resolve().parent / "email_config.json"

# 频率限制存储文件（脚本同目录下）
_RATE_LIMIT_FILE = Path(__file__).resolve().parent / "email_rate_limit.json"

# 日志文件（脚本同目录下）
_LOG_FILE = Path(__file__).resolve().parent / "sendemail.log"

# 必填字段
_REQUIRED_FIELDS = ("name", "smtp_host", "smtp_port", "username", "password")

# 频率限制常量
_HOURLY_LIMIT = 10
_DAILY_LIMIT = 100
_KEEP_DAYS = 14

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d [pid=%(process)d tid=%(thread)d] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logger.addHandler(_file_handler)
logger.propagate = False  # 避免调用方同时配置了 root logger 时重复输出

# 频率限制文件的写入锁，保护并发批量发送时的计数一致性
_rate_limit_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InlineImage:
    """HTML 邮件中通过 CID 引用的内联图片。"""

    cid: str           # Content-ID，不含尖括号，例如 "cpu_chart"
    data: bytes        # 图片原始字节数据
    mimetype: str = "image/png"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    sender_name: str

    def __repr__(self) -> str:
        return (
            f"ProviderConfig(name={self.name!r}, smtp_host={self.smtp_host!r}, "
            f"smtp_port={self.smtp_port!r}, username={self.username!r}, "
            f"password=<redacted>)"
        )


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _load_config(config_path: Path | str | None) -> list[ProviderConfig]:
    """加载并校验配置文件，返回所有 enabled 的 ProviderConfig 列表。"""
    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG

    if not path.exists():
        raise FileNotFoundError(
            f"找不到配置文件：{path}\n"
            f"请复制 email_config.example.json 为 email_config.json 并填写账号信息。"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件 JSON 解析失败：{exc}") from exc

    if not isinstance(data, dict) or "providers" not in data:
        raise ValueError("配置文件格式错误：缺少顶层 'providers' 字段。")

    raw_providers = data["providers"]
    if not isinstance(raw_providers, list):
        raise ValueError("配置文件格式错误：'providers' 必须是数组。")

    enabled: list[ProviderConfig] = []

    for idx, item in enumerate(raw_providers):
        if not isinstance(item, dict):
            raise ValueError(f"providers[{idx}] 格式错误：必须是对象。")

        # 校验必填字段
        for field in _REQUIRED_FIELDS:
            if field not in item:
                raise ValueError(
                    f"providers[{idx}]（name={item.get('name', '未知')!r}）"
                    f"缺少必填字段：'{field}'"
                )

        if not item.get("enabled", False):
            continue

        enabled.append(
            ProviderConfig(
                name=str(item["name"]),
                smtp_host=str(item["smtp_host"]),
                smtp_port=int(item["smtp_port"]),
                username=str(item["username"]),
                password=str(item["password"]),
                sender_name=str(item.get("sender_name", "")),
            )
        )

    if not enabled:
        raise ValueError(
            "配置文件中没有任何 enabled 的 provider，"
            "请在 email_config.json 中将至少一个 provider 的 'enabled' 设为 true。"
        )

    return enabled


def _select_provider(providers: list[ProviderConfig]) -> ProviderConfig:
    """从 enabled 列表中选取 provider；多个时发出警告并取第一个。"""
    if len(providers) > 1:
        names = ", ".join(p.name for p in providers)
        warnings.warn(
            f"存在多个已启用的 provider：{names}。"
            f"将使用第一个：{providers[0].name}。",
            stacklevel=3,
        )
    return providers[0]


def _normalize_addresses(addrs: str | list[str] | None) -> list[str]:
    """将地址参数统一为列表，None 返回空列表。"""
    if addrs is None:
        return []
    if isinstance(addrs, str):
        return [addrs]
    return list(addrs)


def _build_message(
    from_addr: str,
    sender_name: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    bcc: list[str],
    html: bool,
    inline_images: list[InlineImage] | None = None,
) -> Message:
    """构造邮件 Message 对象。有内联图片时使用 multipart/related 结构。"""
    if html and inline_images:
        # multipart/related：HTML 正文 + CID 内联图片
        msg: Message = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name, from_addr)) if sender_name else from_addr
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg.attach(MIMEText(body, "html", "utf-8"))
        for img in inline_images:
            subtype = img.mimetype.split("/", 1)[1]
            part = MIMEImage(img.data, _subtype=subtype)
            part["Content-ID"] = f"<{img.cid}>"
            part["Content-Disposition"] = "inline"
            msg.attach(part)
        return msg

    # 纯文本或无内联图片的 HTML
    email_msg = EmailMessage()
    email_msg["Subject"] = subject
    if sender_name:
        try:
            local, domain = from_addr.rsplit("@", 1)
            email_msg["From"] = Address(display_name=sender_name, username=local, domain=domain)
        except ValueError:
            email_msg["From"] = from_addr
    else:
        email_msg["From"] = from_addr
    email_msg["To"] = ", ".join(to)
    if cc:
        email_msg["Cc"] = ", ".join(cc)
    if bcc:
        email_msg["Bcc"] = ", ".join(bcc)
    content_type = "html" if html else "plain"
    email_msg.set_content(body, subtype=content_type, charset="utf-8")
    return email_msg


def _send_via_smtp(provider: ProviderConfig, message: Message) -> None:
    """发送邮件：端口 465 使用 SSL，其他端口使用 STARTTLS。"""
    try:
        if provider.smtp_port == 465:
            with smtplib.SMTP_SSL(provider.smtp_host, provider.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.login(provider.username, provider.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(provider.smtp_host, provider.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(provider.username, provider.password)
                smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise smtplib.SMTPAuthenticationError(
            exc.smtp_code,
            f"认证失败（{provider.name}）：请检查 email_config.json 中的授权码是否正确。"
            f"注意：QQ 邮箱应填写「授权码」，而非 QQ 登录密码。",
        ) from exc
    except socket.timeout as exc:
        raise RuntimeError(
            f"连接 {provider.smtp_host}:{provider.smtp_port} 超时，"
            f"请检查网络连接。"
        ) from exc


def _load_sent_timestamps(rate_limit_path: Path) -> list[float]:
    """加载发送时间戳列表，过滤掉 24 小时以前的记录。"""
    if not rate_limit_path.exists():
        return []
    try:
        data = json.loads(rate_limit_path.read_text(encoding="utf-8"))
        timestamps = data.get("sent_timestamps", [])
    except (json.JSONDecodeError, OSError):
        return []

    cutoff_24h = time.time() - 86400
    return [ts for ts in timestamps if ts > cutoff_24h]


def _save_sent_timestamps(rate_limit_path: Path, timestamps: list[float]) -> None:
    """将时间戳列表写回文件，只保留最近 14 天的记录。"""
    cutoff = time.time() - _KEEP_DAYS * 86400
    kept = [ts for ts in timestamps if ts > cutoff]
    rate_limit_path.write_text(
        json.dumps({"sent_timestamps": kept}, ensure_ascii=False),
        encoding="utf-8",
    )


def _check_rate_limit(
    rate_limit_path: Path,
    to: list[str],
    subject: str,
) -> list[float]:
    """
    检查发送频率是否超限。

    Returns:
        过滤后的今日时间戳列表（供后续追加使用）。

    Raises:
        RuntimeError: 超出每小时或每天限额。
    """
    today_sent = _load_sent_timestamps(rate_limit_path)

    cutoff_1h = time.time() - 3600
    hour_sent = [ts for ts in today_sent if ts > cutoff_1h]

    if len(hour_sent) >= _HOURLY_LIMIT:
        logger.warning(
            "发送被拦截（每小时限额已达 %d 封）: to=%s subject=%s",
            _HOURLY_LIMIT,
            ", ".join(to),
            subject,
        )
        raise RuntimeError(
            f"发送频率超限：每小时最多发送 {_HOURLY_LIMIT} 封，请稍后再试。"
        )

    if len(today_sent) >= _DAILY_LIMIT:
        logger.warning(
            "发送被拦截（每天限额已达 %d 封）: to=%s subject=%s",
            _DAILY_LIMIT,
            ", ".join(to),
            subject,
        )
        raise RuntimeError(
            f"发送频率超限：每天最多发送 {_DAILY_LIMIT} 封，请明天再试。"
        )

    return today_sent


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    *,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    html: bool = False,
    inline_images: list[InlineImage] | None = None,
    config_path: Path | str | None = None,
    rate_limit_path: Path | str | None = None,
) -> None:
    """
    发送邮件。

    Args:
        to:               收件人，单个地址字符串或地址列表。
        subject:          邮件主题。
        body:             邮件正文。
        cc:               抄送，可选。
        bcc:              密送，可选。
        html:             True 时正文按 HTML 处理（Content-Type: text/html）。
        config_path:      配置文件路径；None 时自动查找脚本同目录的 email_config.json。
        rate_limit_path:  频率限制记录文件路径；None 时使用脚本同目录的 email_rate_limit.json。

    Raises:
        FileNotFoundError:       配置文件不存在。
        ValueError:              配置格式错误或无可用 provider。
        RuntimeError:            发送频率超限或连接超时。
        smtplib.SMTPException:   SMTP 通信失败。
    """
    providers = _load_config(config_path)
    provider = _select_provider(providers)

    to_list = _normalize_addresses(to)
    cc_list = _normalize_addresses(cc)
    bcc_list = _normalize_addresses(bcc)

    rl_path = Path(rate_limit_path) if rate_limit_path is not None else _RATE_LIMIT_FILE

    # 持锁完成限额检查 + 预占槽位，避免并发批量发送时超限
    with _rate_limit_lock:
        today_sent = _check_rate_limit(rl_path, to_list, subject)
        today_sent.append(time.time())
        _save_sent_timestamps(rl_path, today_sent)

    message = _build_message(
        from_addr=provider.username,
        sender_name=provider.sender_name,
        to=to_list,
        subject=subject,
        body=body,
        cc=cc_list,
        bcc=bcc_list,
        html=html,
        inline_images=inline_images,
    )

    try:
        _send_via_smtp(provider, message)
    except Exception as exc:
        logger.error(
            "邮件发送失败: to=%s subject=%s provider=%s error=%s",
            ", ".join(to_list),
            subject,
            provider.name,
            exc,
        )
        raise

    logger.info(
        "邮件已发送: to=%s subject=%s provider=%s",
        ", ".join(to_list),
        subject,
        provider.name,
    )


@dataclass
class EmailTask:
    """批量发送时描述单封邮件的参数。"""

    to: str | list[str]
    subject: str
    body: str
    cc: str | list[str] | None = None
    bcc: str | list[str] | None = None
    html: bool = False


@dataclass
class EmailResult:
    """批量发送中单封邮件的执行结果。"""

    task: EmailTask
    success: bool
    error: Exception | None = field(default=None, repr=False)


async def send_emails_async(
    tasks: list[EmailTask],
    *,
    config_path: Path | str | None = None,
    rate_limit_path: Path | str | None = None,
    max_workers: int = 5,
) -> list[EmailResult]:
    """
    并发发送一批邮件，全部完成后返回结果列表。

    Args:
        tasks:            待发送的邮件列表，每项为一个 EmailTask。
        config_path:      配置文件路径；None 时使用默认路径。
        rate_limit_path:  频率限制记录文件路径；None 时使用默认路径。
        max_workers:      线程池最大并发数，默认 5。

    Returns:
        与 tasks 顺序一一对应的 EmailResult 列表。
        每项包含 success（是否成功）和 error（失败时的异常，成功为 None）。
    """
    def _send_one(task: EmailTask) -> None:
        send_email(
            to=task.to,
            subject=task.subject,
            body=task.body,
            cc=task.cc,
            bcc=task.bcc,
            html=task.html,
            config_path=config_path,
            rate_limit_path=rate_limit_path,
        )

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            loop.run_in_executor(executor, _send_one, task)
            for task in tasks
        ]
        raw_results = await asyncio.gather(*futures, return_exceptions=True)

    results = [
        EmailResult(
            task=task,
            success=not isinstance(r, Exception),
            error=r if isinstance(r, Exception) else None,
        )
        for task, r in zip(tasks, raw_results)
    ]

    succeeded = sum(r.success for r in results)
    logger.info(
        "批量发送完成：共 %d 封，成功 %d 封，失败 %d 封",
        len(results),
        succeeded,
        len(results) - succeeded,
    )
    return results


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="send_email",
        description="发送邮件（推荐使用 QQ 邮箱 SMTP 服务）",
    )
    parser.add_argument(
        "--to",
        dest="to",
        metavar="ADDR",
        action="append",
        required=True,
        help="收件人地址（可多次指定）",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="邮件主题",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument(
        "--body",
        help="邮件正文（字符串）",
    )
    body_group.add_argument(
        "--body-file",
        metavar="PATH",
        help="从文件读取邮件正文",
    )

    parser.add_argument(
        "--cc",
        metavar="ADDR",
        action="append",
        help="抄送地址（可多次指定）",
    )
    parser.add_argument(
        "--bcc",
        metavar="ADDR",
        action="append",
        help="密送地址（可多次指定）",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="正文按 HTML 格式处理",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="配置文件路径（默认：脚本同目录的 email_config.json）",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            logger.error("正文文件不存在：%s", body_path)
            sys.exit(1)
        body = body_path.read_text(encoding="utf-8")
    else:
        body = args.body

    try:
        send_email(
            to=args.to,
            subject=args.subject,
            body=body,
            cc=args.cc,
            bcc=args.bcc,
            html=args.html,
            config_path=args.config,
        )
    except Exception as exc:
        logger.error("发送失败：%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
