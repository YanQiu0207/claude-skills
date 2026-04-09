"""
单向同步 ~/.claude/skills/ -> claude-skills 仓库。

同步规则：
- 技能目录 = 包含 SKILL.md 的子目录
- 源文件更新 -> 覆盖仓库文件
- 仓库文件更新 -> 不覆盖，记录冲突
- 源有新技能/新文件 -> 复制到仓库
- 不删除仓库中已有的文件
- 同步后自动 git commit（有变更时）
- 无变更时也记录日志

通过 Windows 任务计划程序定时调用，每次执行一次后退出。
"""

import logging
import shutil
import subprocess
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"
REPO_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_DIR / "scripts" / "sync.log"


def setup_logging():
    logger = logging.getLogger("sync-skills")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def find_skills(base: Path) -> dict[str, Path]:
    skills = {}
    if not base.is_dir():
        return skills
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            skills[d.name] = d
    return skills


def sync() -> tuple[list[str], list[str]]:
    """返回 (已同步文件, 冲突文件)。"""
    synced = []
    conflicts = []

    for name, src_dir in find_skills(SKILLS_DIR).items():
        dst_dir = REPO_DIR / name

        for src_file in src_dir.rglob("*"):
            if not src_file.is_file() or "__pycache__" in src_file.parts:
                continue

            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel

            if not dst_file.exists():
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                synced.append(f"{name}/{rel}")
            elif src_file.stat().st_mtime > dst_file.stat().st_mtime:
                shutil.copy2(src_file, dst_file)
                synced.append(f"{name}/{rel}")
            elif dst_file.stat().st_mtime > src_file.stat().st_mtime:
                conflicts.append(f"{name}/{rel}")

    return synced, conflicts


def git_commit(synced: list[str]):
    subprocess.run(["git", "add", "-A"], cwd=REPO_DIR, check=True)

    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR)
    if result.returncode == 0:
        return False

    msg = f"同步 {len(synced)} 个文件\n\n" + "\n".join(synced)
    subprocess.run(["git", "commit", "-m", msg], cwd=REPO_DIR, check=True)
    return True


def main():
    logger = setup_logging()
    logger.info("===== 开始同步 =====")
    logger.info("源: %s", SKILLS_DIR)
    logger.info("目标: %s", REPO_DIR)

    try:
        synced, conflicts = sync()

        if synced:
            logger.info("同步 %d 个文件:", len(synced))
            for f in synced:
                logger.info("  已同步: %s", f)
            if git_commit(synced):
                logger.info("已提交到 git（%d 个文件）", len(synced))
        else:
            logger.info("无变更，跳过提交")

        if conflicts:
            logger.warning("冲突 %d 个文件（仓库侧更新，未覆盖）:", len(conflicts))
            for f in conflicts:
                logger.warning("  冲突: %s", f)

    except Exception:
        logger.exception("同步失败")
        raise

    logger.info("===== 同步结束 =====")


if __name__ == "__main__":
    main()
