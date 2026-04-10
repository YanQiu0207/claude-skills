"""
将本地路径按映射规则单向同步到当前仓库。

同步规则：
- 从 scripts/sync-pathmap.json 读取映射配置。
- 每条映射支持 enabled/source/target 三个字段。
- 支持“文件 -> 文件”和“目录 -> 目录”两种映射方式。
- 支持同步任意目录或文件，不限于 Claude skills。
- 如果源文件比目标文件新，则覆盖目标文件。
- 如果目标文件比源文件新，则保留目标文件并记录为冲突。
- 如果源侧存在新文件，则复制到仓库。
- 如果源侧文件已删除，则同步删除目标侧对应的文件。
- 发生变更时，自动执行 git commit + push。
- 没有变更时，也会照常写入日志。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_DIR / "scripts" / "sync-pathmap.json"
LOG_FILE = REPO_DIR / "scripts" / "sync.log"
IGNORED_DIR_NAMES = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class SyncMapping:
    enabled: bool
    raw_source: str
    raw_target: str
    source: Path | None
    target: Path | None


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("sync-paths")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    existing_log_files = {
        Path(getattr(handler, "baseFilename", "")).resolve()
        for handler in logger.handlers
        if isinstance(handler, logging.FileHandler)
    }
    if LOG_FILE.resolve() not in existing_log_files:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def resolve_config_path(raw_path: str) -> Path:
    expanded = os.path.expandvars(raw_path)
    path = Path(expanded).expanduser()
    if path.is_absolute():
        return path
    return (REPO_DIR / path).resolve()


def format_target_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_DIR))
    except ValueError:
        return str(path)


def ensure_target_in_repo(target: Path, mapping_index: int) -> None:
    try:
        target.relative_to(REPO_DIR)
    except ValueError as exc:
        raise ValueError(
            f"第 {mapping_index} 条映射的 target 必须位于仓库内: {target}"
        ) from exc


def load_sync_mappings(config_file: Path = CONFIG_FILE) -> list[SyncMapping]:
    if not config_file.exists():
        raise FileNotFoundError(f"未找到同步配置文件: {config_file}")

    data = json.loads(config_file.read_text(encoding="utf-8"))
    entries = data.get("mappings") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("同步配置必须是 JSON 数组，或包含 'mappings' 字段的对象。")

    mappings: list[SyncMapping] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"第 {index} 条映射必须是 JSON 对象。")

        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"第 {index} 条映射的 'enabled' 必须是 true 或 false。")

        raw_source = entry.get("source")
        raw_target = entry.get("target")
        if not isinstance(raw_source, str) or not raw_source.strip():
            raise ValueError(f"第 {index} 条映射缺少合法的 'source'。")
        if not isinstance(raw_target, str) or not raw_target.strip():
            raise ValueError(f"第 {index} 条映射缺少合法的 'target'。")

        if not enabled:
            mappings.append(
                SyncMapping(
                    enabled=False,
                    raw_source=raw_source,
                    raw_target=raw_target,
                    source=None,
                    target=None,
                )
            )
            continue

        source = resolve_config_path(raw_source)
        target = resolve_config_path(raw_target)
        ensure_target_in_repo(target, index)

        mappings.append(
            SyncMapping(
                enabled=True,
                raw_source=raw_source,
                raw_target=raw_target,
                source=source,
                target=target,
            )
        )

    return mappings


def should_skip_file(path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in path.parts) or path.suffix in IGNORED_SUFFIXES


def sync_one_file(source_file: Path, target_file: Path) -> tuple[bool, bool]:
    if target_file.exists() and target_file.is_dir():
        raise ValueError(f"目标路径是目录，但源路径是文件: {target_file}")

    if not target_file.exists():
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        return True, False

    source_mtime = source_file.stat().st_mtime_ns
    target_mtime = target_file.stat().st_mtime_ns

    if source_mtime > target_mtime:
        shutil.copy2(source_file, target_file)
        return True, False
    if target_mtime > source_mtime:
        return False, True
    return False, False


def sync_directory(source_dir: Path, target_dir: Path) -> tuple[list[str], list[str], list[str]]:
    synced: list[str] = []
    conflicts: list[str] = []

    if target_dir.exists() and target_dir.is_file():
        raise ValueError(f"目标路径是文件，但源路径是目录: {target_dir}")

    for source_file in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
        if not source_file.is_file() or should_skip_file(source_file):
            continue

        relative_path = source_file.relative_to(source_dir)
        target_file = target_dir / relative_path
        is_synced, is_conflict = sync_one_file(source_file, target_file)
        label = format_target_label(target_file)

        if is_synced:
            synced.append(label)
        elif is_conflict:
            conflicts.append(label)

    deleted: list[str] = []
    if target_dir.exists():
        for target_file in sorted(target_dir.rglob("*"), key=lambda item: item.as_posix()):
            if not target_file.is_file() or should_skip_file(target_file):
                continue
            relative_path = target_file.relative_to(target_dir)
            source_file = source_dir / relative_path
            if not source_file.exists():
                target_file.unlink()
                deleted.append(format_target_label(target_file))

        for dir_path in sorted(target_dir.rglob("*"), key=lambda item: item.as_posix(), reverse=True):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()

    return synced, conflicts, deleted


def sync_file(source_file: Path, target_file: Path) -> tuple[list[str], list[str], list[str]]:
    is_synced, is_conflict = sync_one_file(source_file, target_file)
    label = format_target_label(target_file)
    synced = [label] if is_synced else []
    conflicts = [label] if is_conflict else []
    return synced, conflicts, []


def sync_mappings(mappings: list[SyncMapping], logger: logging.Logger) -> tuple[list[str], list[str], list[str]]:
    synced: list[str] = []
    conflicts: list[str] = []
    deleted: list[str] = []

    for index, mapping in enumerate(mappings, start=1):
        if not mapping.enabled:
            logger.info(
                "映射 %d/%d 已禁用，已跳过: %s -> %s",
                index,
                len(mappings),
                mapping.raw_source,
                mapping.raw_target,
            )
            continue

        if mapping.source is None or mapping.target is None:
            raise RuntimeError(f"第 {index} 条启用映射缺少解析后的路径。")

        logger.info(
            "映射 %d/%d: %s -> %s",
            index,
            len(mappings),
            mapping.source,
            mapping.target,
        )

        if not mapping.source.exists():
            logger.warning("源路径不存在，已跳过: %s", mapping.source)
            continue

        if mapping.source.is_file():
            mapping_synced, mapping_conflicts, mapping_deleted = sync_file(mapping.source, mapping.target)
        elif mapping.source.is_dir():
            mapping_synced, mapping_conflicts, mapping_deleted = sync_directory(mapping.source, mapping.target)
        else:
            logger.warning("不支持的源路径类型，已跳过: %s", mapping.source)
            continue

        synced.extend(mapping_synced)
        conflicts.extend(mapping_conflicts)
        deleted.extend(mapping_deleted)

    return synced, conflicts, deleted


def update_readme_with_claude(logger: logging.Logger) -> None:
    """调用 Claude Code CLI 全面更新 README.md。"""
    prompt = (
        "全面更新 README.md，使其与仓库当前状态一致。\n\n"
        "## 信息采集\n\n"
        "1. 扫描 skills/ 下每个子目录的 SKILL.md，读取 YAML frontmatter 中的 name 和 description\n"
        "2. 扫描 agents/ 下的 .md 文件，读取 YAML frontmatter 中的 name 和 description\n"
        "3. 读取 claude_ref/ 下的每个文件，了解其用途\n"
        "4. 读取 CLAUDE.md，了解全局指令内容\n"
        "5. 扫描每个 SKILL.md 正文，提取依赖关系：\n"
        "   - 调用了哪些其他 skill（关键词：Skill 工具、调用 xxx 技能）\n"
        "   - 调用了哪些 agent（关键词：worker agent、xxx-worker）\n"
        "   - 引用了 claude_ref/ 下的哪些参考文件（关键词：CLAUDE.md 中的、规范文件）\n"
        "6. 读取 scripts/sync-pathmap.json 了解实际同步映射配置\n\n"
        "## 更新范围\n\n"
        "逐一检查 README.md 中的以下章节，将过时内容更新为采集到的实际信息：\n\n"
        "- **Skills 列表**：表格内容与扫描结果对齐，按名称排序，description 过长取第一句\n"
        "- **Agents 列表**：同上\n"
        "- **参考文件（claude_ref）**：列出 claude_ref/ 下每个文件的用途及被哪些 skill 引用（三列表格：文件、说明、被引用方）\n"
        "- **全局指令（CLAUDE.md）**：简要描述 CLAUDE.md 的核心配置内容\n"
        "- **目录结构**：与仓库顶层实际目录一致\n"
        "- **安装方式**：复制命令覆盖所有需要安装的目录（skills、agents、claude_ref 等），CLAUDE.md 需提示不要覆盖本地已有文件\n"
        "- **依赖关系**：用树状图展示完整依赖链，包括 skill、agent、参考文件三类依赖\n"
        "- **路径同步脚本**：示例 JSON 与 sync-pathmap.json 的实际格式和字段一致（不要照搬真实路径，用示意性内容）\n\n"
        "## 规则\n\n"
        "- 保持 README 现有的章节结构和排版风格\n"
        "- 不新增、不删除、不重排章节\n"
        "- 如果某个章节内容已经是最新的，不要修改它\n"
        "- 如果整个 README 都不需要改动，不要修改文件"
    )

    try:
        logger.info("正在尝试通过 Claude Code 更新 README.md")
        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--model", "sonnet",
                "--allowedTools", "Read,Edit,Glob,Grep",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )
        if result.returncode == 0:
            logger.info("已通过 Claude Code 更新 README.md")
        else:
            logger.warning("Claude Code 更新 README 失败: %s", result.stderr.strip())
    except FileNotFoundError:
        logger.warning("未找到 claude 命令，跳过 README 更新")
    except subprocess.TimeoutExpired:
        logger.warning("Claude Code 调用超时（120s），跳过 README 更新")
    except Exception:
        logger.warning("Claude Code 更新 README 异常，跳过", exc_info=True)


def git_commit_and_push(synced: list[str], deleted: list[str], logger: logging.Logger) -> bool:
    subprocess.run(["git", "add", "-A"], cwd=REPO_DIR, check=True)

    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR)
    if result.returncode == 0:
        return False

    changed = len(synced) + len(deleted)
    details: list[str] = list(synced)
    details.extend(f"[删除] {item}" for item in deleted)
    message = f"脚本按映射自动同步 {changed} 个文件\n\n" + "\n".join(details)
    subprocess.run(["git", "commit", "-m", message], cwd=REPO_DIR, check=True)

    result = subprocess.run(
        ["git", "push"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        logger.info("已推送到远程仓库")
    else:
        logger.warning("推送失败: %s", result.stderr.strip())

    return True


def cleanup_old_logs(logger: logging.Logger) -> None:
    if not LOG_FILE.exists():
        return

    cutoff = datetime.now() - timedelta(days=30)
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    last_expired = -1

    for index in range(len(lines) - 1, -1, -1):
        try:
            timestamp = datetime.strptime(lines[index][:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            continue

        if timestamp < cutoff:
            last_expired = index
            break

    if last_expired >= 0:
        kept_lines = lines[last_expired + 1 :]
        LOG_FILE.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
        logger.info("已清理 %d 条过期日志（超过 30 天）", last_expired + 1)


def main() -> None:
    logger = setup_logging()
    cleanup_old_logs(logger)
    logger.info("===== 开始同步 =====")
    logger.info("配置文件: %s", CONFIG_FILE)
    logger.info("目标仓库: %s", REPO_DIR)

    try:
        mappings = load_sync_mappings()
        enabled_count = sum(mapping.enabled for mapping in mappings)
        logger.info(
            "已加载 %d 条映射（启用 %d 条，禁用 %d 条）",
            len(mappings),
            enabled_count,
            len(mappings) - enabled_count,
        )

        synced, conflicts, deleted = sync_mappings(mappings, logger)

        # if synced or deleted:
        #     update_readme_with_claude(logger)

        if synced or deleted:
            if synced:
                logger.info("已同步 %d 个文件", len(synced))
                for item in synced:
                    logger.info("  已同步: %s", item)
            if deleted:
                logger.info("已删除 %d 个文件", len(deleted))
                for item in deleted:
                    logger.info("  已删除: %s", item)
            if git_commit_and_push(synced, deleted, logger):
                logger.info("已提交到 git（%d 个文件）", len(synced) + len(deleted))
        else:
            logger.info("没有变更，跳过 git 提交")

        if conflicts:
            logger.warning(
                "发现 %d 个冲突文件（目标文件比源文件新，已保留目标文件）",
                len(conflicts),
            )
            for item in conflicts:
                logger.warning("  冲突: %s", item)

    except Exception:
        logger.exception("同步失败")
        raise

    logger.info("===== 同步结束 =====")


if __name__ == "__main__":
    main()
