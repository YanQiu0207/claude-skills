#!/usr/bin/env python3
"""
服务器状态快照采集脚本。

采集当前时刻的 CPU、内存、磁盘分区与短时间窗口内的磁盘 I/O 情况，
生成 HTML 报告，并通过 send_email.py 发送到指定邮箱。

设计原则：
- 不在运行时尝试交互式提权，适合挂到后台定时任务执行
- 磁盘 I/O 使用采样窗口内的增量，而不是进程启动以来的累计值
- 权限不足时按 best-effort 降级，只有显式要求时才失败退出

依赖：
    pip install psutil matplotlib

用法：
    python collect_server_stats.py --to you@example.com
    python collect_server_stats.py --to foo@example.com --subject "今日巡检"
    python collect_server_stats.py --to foo@example.com --config /path/to/email_config.json
    python collect_server_stats.py --to foo@example.com --io-interval 2 --require-disk-io
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import psutil

_SCRIPT_DIR = Path(__file__).resolve().parent
_LOG_FILE = _SCRIPT_DIR / "collect_server_stats.log"
TOP_N = 10

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from send_email import InlineImage, send_email as _send_email  # noqa: E402


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(_LOG_FILE, encoding="utf-8")],
    )


def _setup_matplotlib_fonts() -> None:
    plt.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "PingFang SC",
        "WenQuanYi Micro Hei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def _fmt_bytes(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _fmt_seconds(seconds: float) -> str:
    return f"{seconds:g} 秒"


def collect_cpu_stats() -> tuple[float, list[tuple[str, float]]]:
    """
    采集 CPU 使用情况，使用 1 秒观察窗口。

    Returns:
        (系统总 CPU%, [(进程名, CPU%)])，按 CPU% 降序排列
    """
    live_procs: list[psutil.Process] = []
    for proc in psutil.process_iter(["name"]):
        try:
            proc.cpu_percent(interval=None)
            live_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    total_cpu = psutil.cpu_percent(interval=1)

    cpu_by_name: dict[str, float] = {}
    for proc in live_procs:
        try:
            name = proc.name() or "Unknown"
            cpu = proc.cpu_percent(interval=None)
            cpu_by_name[name] = cpu_by_name.get(name, 0.0) + cpu
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    sorted_procs = sorted(cpu_by_name.items(), key=lambda x: x[1], reverse=True)
    return total_cpu, sorted_procs


def collect_memory_stats() -> tuple[int, int, float, list[tuple[str, int]]]:
    """
    采集内存使用情况。

    Returns:
        (总内存 bytes, 已用 bytes, 利用率, [(进程名, RSS bytes)])，按 RSS 降序排列
    """
    vm = psutil.virtual_memory()
    mem_by_name: dict[str, int] = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = proc.info["name"] or "Unknown"
            mem_info = proc.info["memory_info"]
            rss = mem_info.rss if mem_info else 0
            mem_by_name[name] = mem_by_name.get(name, 0) + rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    sorted_procs = sorted(mem_by_name.items(), key=lambda x: x[1], reverse=True)
    return vm.total, vm.used, vm.percent, sorted_procs


def _snapshot_process_io() -> dict[int, tuple[str, int]]:
    """Capture cumulative read/write bytes for each accessible PID."""
    snapshot: dict[int, tuple[str, int]] = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            counters = proc.io_counters()
            name = proc.info["name"] or "Unknown"
            total = counters.read_bytes + counters.write_bytes
            snapshot[proc.pid] = (name, total)
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, NotImplementedError):
            pass
    return snapshot


def collect_disk_io_stats(interval: float = 1.0) -> tuple[bool, list[tuple[str, int]]]:
    """
    采集磁盘 I/O 使用情况，统计采样窗口内的读写增量。

    Returns:
        (是否有数据, [(进程名, delta bytes)])，按增量降序排列
    """
    interval = max(interval, 0.0)
    before = _snapshot_process_io()
    if interval > 0:
        time.sleep(interval)
    after = _snapshot_process_io()

    if not before or not after:
        return False, []

    io_by_name: dict[str, int] = {}
    for pid in before.keys() & after.keys():
        start_name, start_total = before[pid]
        end_name, end_total = after[pid]
        delta = max(0, end_total - start_total)
        name = end_name or start_name or "Unknown"
        io_by_name[name] = io_by_name.get(name, 0) + delta

    sorted_procs = sorted(io_by_name.items(), key=lambda x: x[1], reverse=True)
    return True, sorted_procs


def collect_disk_partitions() -> list[dict[str, str | int | float]]:
    result: list[dict[str, str | int | float]] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            result.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
        except (PermissionError, OSError):
            pass
    return result


def make_pie_chart(items: Sequence[tuple[str, float | int]], title: str) -> bytes | None:
    if not items:
        return None

    top = items[:TOP_N]
    rest_sum = sum(v for _, v in items[TOP_N:])

    labels = [name for name, _ in top]
    values = [float(v) for _, v in top]
    if rest_sum > 0:
        labels.append("其他")
        values.append(float(rest_sum))

    pairs = [(label, value) for label, value in zip(labels, values) if value > 0]
    if not pairs:
        return None

    labels, values = zip(*pairs)
    labels = [label[:22] + "..." if len(label) > 22 else label for label in labels]

    fig, ax = plt.subplots(figsize=(9, 6))
    _, texts, autotexts = ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.8,
    )
    for text in texts:
        text.set_fontsize(9)
    for autotext in autotexts:
        autotext.set_fontsize(8)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=14)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    background: #f0f2f5; color: #333;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.ts { font-size: 13px; color: #888; margin-bottom: 24px; }
.cards { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }
.card {
    flex: 1; min-width: 160px; background: #fff; border-radius: 10px;
    padding: 18px 22px; box-shadow: 0 2px 8px rgba(0,0,0,.07);
}
.lbl { font-size: 12px; color: #888; text-transform: uppercase; margin-bottom: 6px; }
.val { font-size: 28px; font-weight: 700; color: #1a1a2e; }
.sub { font-size: 12px; color: #aaa; margin-top: 4px; }
section {
    background: #fff; border-radius: 10px; padding: 22px 24px;
    margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,.07);
}
h2 {
    font-size: 16px; font-weight: 700; margin-bottom: 16px;
    border-left: 4px solid #5b8dee; padding-left: 10px;
}
.chart { text-align: center; margin-bottom: 16px; }
.chart img { max-width: 100%; border-radius: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
    background: #f7f8fa; text-align: left; padding: 8px 12px;
    font-weight: 600; color: #555; border-bottom: 2px solid #e8e8e8;
}
td { padding: 7px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f9fbff; }
.bar-wrap {
    display: inline-block; width: 90px; height: 8px; background: #eee;
    border-radius: 4px; vertical-align: middle; margin-right: 6px; overflow: hidden;
}
.bar { display: block; height: 100%; border-radius: 4px; }
.pct-lbl { font-size: 12px; vertical-align: middle; }
.warn {
    color: #e65100; background: #fff3e0; border-radius: 6px;
    padding: 12px 16px; font-size: 13px;
}
.note {
    color: #455a64; background: #eceff1; border-radius: 6px;
    padding: 12px 16px; font-size: 13px;
}
"""


def _stat_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    return (
        f'<div class="card">'
        f'<div class="lbl">{escape(label)}</div>'
        f'<div class="val">{escape(value)}</div>'
        f"{sub_html}</div>"
    )


def _pct_bar(pct: float) -> str:
    color = "#4caf50" if pct < 70 else "#ff9800" if pct < 90 else "#f44336"
    return (
        f'<span class="bar-wrap">'
        f'<span class="bar" style="width:{pct:.1f}%;background:{color}"></span>'
        f"</span>"
        f'<span class="pct-lbl">{pct:.1f}%</span>'
    )


def _rows_cpu(procs: list[tuple[str, float]]) -> str:
    return "".join(
        f"<tr><td>{i + 1}</td><td>{escape(name)}</td><td>{val:.1f}%</td></tr>"
        for i, (name, val) in enumerate(procs[:TOP_N])
    )


def _rows_mem(procs: list[tuple[str, int]]) -> str:
    return "".join(
        f"<tr><td>{i + 1}</td><td>{escape(name)}</td><td>{_fmt_bytes(val)}</td></tr>"
        for i, (name, val) in enumerate(procs[:TOP_N])
    )


def _rows_io(procs: list[tuple[str, int]]) -> str:
    return "".join(
        f"<tr><td>{i + 1}</td><td>{escape(name)}</td><td>{_fmt_bytes(val)}</td></tr>"
        for i, (name, val) in enumerate(procs[:TOP_N])
    )


def build_html(
    timestamp: str,
    cpu_total: float,
    cpu_procs: list[tuple[str, float]],
    cpu_cid: str | None,
    mem_total: int,
    mem_used: int,
    mem_pct: float,
    mem_procs: list[tuple[str, int]],
    mem_cid: str | None,
    io_ok: bool,
    io_procs: list[tuple[str, int]],
    io_cid: str | None,
    io_window_seconds: float,
    disks: list[dict[str, str | int | float]],
) -> str:
    cpu_chart_html = (
        f'<div class="chart"><img src="cid:{cpu_cid}" alt="CPU 饼状图"></div>'
        if cpu_cid
        else ""
    )
    mem_chart_html = (
        f'<div class="chart"><img src="cid:{mem_cid}" alt="内存饼状图"></div>'
        if mem_cid
        else ""
    )

    if io_ok:
        io_chart_html = (
            f'<div class="chart"><img src="cid:{io_cid}" alt="磁盘 I/O 饼状图"></div>'
            if io_cid
            else ""
        )
        if io_procs:
            io_body = f"""
    {io_chart_html}
    <table>
      <thead><tr><th>排名</th><th>程序名</th><th>I/O 增量</th></tr></thead>
      <tbody>{_rows_io(io_procs)}</tbody>
    </table>"""
        else:
            io_body = """
    <p class="note">采样窗口内未观察到明显的进程磁盘 I/O 活动。</p>"""

        io_section = f"""
  <section>
    <h2>磁盘 I/O（采样窗口 {_fmt_seconds(io_window_seconds)}）</h2>
    {io_body}
  </section>"""
    else:
        io_section = """
  <section>
    <h2>磁盘 I/O</h2>
    <p class="warn">当前运行环境无法获取磁盘 I/O 快照。若该指标是硬要求，请在任务计划中配置更高权限，而不是依赖脚本运行时提权。</p>
  </section>"""

    disk_rows = "".join(
        f"<tr>"
        f"<td>{escape(str(d['device']))}</td>"
        f"<td>{escape(str(d['mountpoint']))}</td>"
        f"<td>{escape(str(d['fstype']))}</td>"
        f"<td>{_fmt_bytes(float(d['total']))}</td>"
        f"<td>{_fmt_bytes(float(d['used']))}</td>"
        f"<td>{_fmt_bytes(float(d['free']))}</td>"
        f"<td>{_pct_bar(float(d['percent']))}</td>"
        f"</tr>"
        for d in disks
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>服务器状态报告 {escape(timestamp)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>服务器状态报告</h1>
  <div class="ts">采集时间：{escape(timestamp)}</div>

  <div class="cards">
    {_stat_card("CPU 利用率", f"{cpu_total:.1f}%")}
    {_stat_card("内存利用率", f"{mem_pct:.1f}%", f"{_fmt_bytes(mem_used)} / {_fmt_bytes(mem_total)}")}
    {_stat_card("磁盘分区", str(len(disks)), "个")}
  </div>

  <section>
    <h2>CPU 利用率（总计 {cpu_total:.1f}%）</h2>
    {cpu_chart_html}
    <table>
      <thead><tr><th>排名</th><th>程序名</th><th>CPU%</th></tr></thead>
      <tbody>{_rows_cpu(cpu_procs)}</tbody>
    </table>
  </section>

  <section>
    <h2>内存利用率（总计 {mem_pct:.1f}%：{_fmt_bytes(mem_used)} / {_fmt_bytes(mem_total)}）</h2>
    {mem_chart_html}
    <table>
      <thead><tr><th>排名</th><th>程序名</th><th>内存占用</th></tr></thead>
      <tbody>{_rows_mem(mem_procs)}</tbody>
    </table>
  </section>

  {io_section}

  <section>
    <h2>磁盘分区详情（共 {len(disks)} 个）</h2>
    <table>
      <thead>
        <tr>
          <th>设备</th><th>挂载点</th><th>文件系统</th>
          <th>总容量</th><th>已使用</th><th>可用</th><th>使用率</th>
        </tr>
      </thead>
      <tbody>{disk_rows}</tbody>
    </table>
  </section>
</div>
</body>
</html>"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collect_server_stats",
        description="采集服务器状态并通过邮件发送 HTML 报告",
    )
    parser.add_argument(
        "--to",
        required=True,
        metavar="ADDR",
        action="append",
        help="收件人邮箱，可重复指定多个",
    )
    parser.add_argument(
        "--subject",
        default="",
        help="邮件主题，留空则自动生成",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="email_config.json 路径，默认使用脚本同目录下的配置",
    )
    parser.add_argument(
        "--io-interval",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="磁盘 I/O 采样窗口秒数，默认 1.0",
    )
    parser.add_argument(
        "--require-disk-io",
        action="store_true",
        help="如果拿不到磁盘 I/O 数据则直接失败退出",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.io_interval < 0:
        parser.error("--io-interval must be >= 0")

    _setup_logging()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = args.subject or f"服务器状态报告 - {timestamp}"

    _setup_matplotlib_fonts()

    logging.info("采集 CPU 数据（约 1 秒）...")
    cpu_total, cpu_procs = collect_cpu_stats()
    logging.info("CPU 利用率：%.1f%%", cpu_total)

    logging.info("采集内存数据...")
    mem_total, mem_used, mem_pct, mem_procs = collect_memory_stats()
    logging.info(
        "内存利用率：%.1f%%，已用 %s / 总 %s",
        mem_pct,
        _fmt_bytes(mem_used),
        _fmt_bytes(mem_total),
    )

    logging.info("采集磁盘 I/O 数据（采样窗口 %s）...", _fmt_seconds(args.io_interval))
    io_ok, io_procs = collect_disk_io_stats(interval=args.io_interval)
    if io_ok:
        logging.info("磁盘 I/O 数据可用。")
    else:
        logging.warning(
            "当前运行环境无法获取磁盘 I/O 快照。"
            "如需该指标，请在任务计划中配置更高权限。"
        )
        if args.require_disk_io:
            logging.error("指定了 --require-disk-io，因磁盘 I/O 数据不可用而退出。")
            sys.exit(2)

    logging.info("采集磁盘分区数据...")
    disks = collect_disk_partitions()
    logging.info("共 %d 个分区。", len(disks))

    logging.info("生成图表...")
    cpu_png = make_pie_chart(cpu_procs, f"CPU 利用率分布（总计 {cpu_total:.1f}%）")
    mem_png = make_pie_chart(mem_procs, f"内存占用分布（总计 {mem_pct:.1f}%）")
    io_png = (
        make_pie_chart(io_procs, f"磁盘 I/O 分布（采样窗口 {_fmt_seconds(args.io_interval)}）")
        if io_ok and io_procs
        else None
    )

    inline_images: list[InlineImage] = []
    cpu_cid = mem_cid = io_cid = None
    if cpu_png:
        cpu_cid = "cpu_chart"
        inline_images.append(InlineImage(cid=cpu_cid, data=cpu_png))
    if mem_png:
        mem_cid = "mem_chart"
        inline_images.append(InlineImage(cid=mem_cid, data=mem_png))
    if io_png:
        io_cid = "io_chart"
        inline_images.append(InlineImage(cid=io_cid, data=io_png))

    logging.info("生成 HTML 报告...")
    html = build_html(
        timestamp=timestamp,
        cpu_total=cpu_total,
        cpu_procs=cpu_procs,
        cpu_cid=cpu_cid,
        mem_total=mem_total,
        mem_used=mem_used,
        mem_pct=mem_pct,
        mem_procs=mem_procs,
        mem_cid=mem_cid,
        io_ok=io_ok,
        io_procs=io_procs,
        io_cid=io_cid,
        io_window_seconds=args.io_interval,
        disks=disks,
    )

    logging.info("发送邮件至：%s ...", ", ".join(args.to))
    try:
        _send_email(
            to=args.to,
            subject=subject,
            body=html,
            html=True,
            inline_images=inline_images or None,
            config_path=args.config,
        )
        logging.info("邮件发送成功。")
    except Exception as exc:
        logging.error("邮件发送失败：%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
