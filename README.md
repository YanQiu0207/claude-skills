# Claude Code Config

个人 Claude Code 配置同步仓库，包含自定义的 Skills 和 Agents。

## Skills 列表

| Skill | 说明 |
|-------|------|
| **batch-md-fmt** | 批量对多个 Markdown 文件进行一站式标准化：先排版规范化，再网络图片本地化。 |
| **batch-md-lint** | 批量检查多个 Markdown 文件的排版规范。 |
| **md-fmt** | 对单个 Markdown 文件进行一站式标准化：先排版规范化，再网络图片本地化。 |
| **md-img-local** | 将Markdown文件中的网络图片自动下载到本地assets目录，添加唯一前缀避免重名冲突，自动替换原文件中的图片链接为本地相对路径。 |
| **pdf2md** | 将 PDF 忠实转换为 Markdown，最大限度保留原文内容、顺序、层级、列表、链接、图示位置与页面信息。 |
| **resume-reviewing** | 用于检查、润色和优化简历内容，提升表达质量。 |
| **skill-del** | 安全删除 skill，自动扫描并处理所有依赖关系（其他 skill、agent 中的引用），确保删除后系统一致。 |
| **skill-rename** | 为 skill 改名，同时自动检查和更新所有依赖关系。 |

## Agents 列表

| Agent | 说明 |
|-------|------|
| **md-fmt-worker** | 对单个 Markdown 文件执行标准化处理（排版 + 图片本地化），供 batch-md-fmt 并行调度使用。 |
| **md-lint** | 检查 Markdown 文件的排版是否符合指定规范文件，自动修复问题并输出总结。 |
| **resume-reviewer** | 审核和评估简历，并提供修改建议。 |

## 安装方式

将需要的 skill / agent 目录或文件复制到 `~/.claude/` 对应目录下即可：

```bash
# 克隆仓库
git clone <repo-url> claude-config

# 复制单个 skill
cp -r claude-config/skills/md-zh ~/.claude/skills/

# 复制全部 skills
cp -r claude-config/skills/* ~/.claude/skills/

# 复制全部 agents
cp -r claude-config/agents/* ~/.claude/agents/
```

Windows 用户：

```powershell
# 复制单个 skill
Copy-Item -Recurse claude-config\skills\md-zh $env:USERPROFILE\.claude\skills\

# 复制全部 skills
Copy-Item -Recurse claude-config\skills\* $env:USERPROFILE\.claude\skills\

# 复制全部 agents
Copy-Item -Recurse claude-config\agents\* $env:USERPROFILE\.claude\agents\
```

## 依赖关系

```text
md-fmt
├── md-zh
└── md-img-local
```

- `md-fmt` 依赖 `md-zh` 和 `md-img-local`，使用前需要同时安装这两个 skill。
- 其他 skill 可以独立使用。

## 开发设置

克隆后启用 pre-commit hook，避免敏感信息被误提交：

```bash
git config core.hooksPath .githooks
cp .githooks/sensitive-patterns.example .githooks/sensitive-patterns
# 编辑 sensitive-patterns，填入你自己的敏感信息模式
```

## 使用注意

- `resume-reviewing` skill 的 `SKILL.md` 可能包含个人求职背景信息，使用前请按自己的情况修改。
- `resume-reviewer` agent 同理，使用前请根据自己的情况调整 prompt 内容。

## 路径同步脚本

仓库内提供了 `scripts/sync-paths.py`，用于按映射规则将任意本地目录或文件单向同步到当前仓库。

同步配置位于 `scripts/sync-pathmap.json`，脚本会按配置中的顺序依次执行同步。每条映射包含以下字段：

```json
{
  "mappings": [
    {
      "enabled": true,
      "source": "~/.claude/skills/md-zh",
      "target": "md-zh"
    },
    {
      "enabled": false,
      "source": "~/.claude/skills/shared/prompt.md",
      "target": "docs/prompt.md"
    }
  ]
}
```

- `enabled`：可选，是否启用该映射；默认值为 `true`。当值为 `false` 时，脚本会跳过该映射。
- `source`：源目录或源文件，支持 `~`、环境变量和绝对路径。
- `target`：仓库内的目标目录或目标文件，推荐写仓库相对路径。
- 目录到目录：递归同步目录内文件。
- 文件到文件：同步单个文件。

同步规则：

- 源文件比目标文件新时，覆盖目标文件。
- 目标文件比源文件新时，不覆盖，记为冲突。
- 源侧文件已删除时，同步删除目标侧对应的文件。
- 有变更时自动执行 `git add`、`git commit`、`git push`。

运行方式：

```bash
python scripts/sync-paths.py
```

如果只需要暂时停用某条同步规则，将对应映射的 `enabled` 设为 `false` 即可，无需改 Python 脚本。
