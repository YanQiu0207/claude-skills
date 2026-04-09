# Claude Code Skills

个人自定义的 Claude Code Skills 集合。

## Skills 列表

| Skill | 说明 |
|-------|------|
| **md-zh** | Markdown 中文排版规范（中英文空格、全角标点、专有名词大小写等） |
| **md-img-local** | 将 Markdown 中的网络图片下载到本地 `assets/` 目录，自动替换链接 |
| **md-fmt** | 一站式 Markdown 标准化：先排版规范化（md-zh），再图片本地化（md-img-local） |
| **pdf2md** | 将 PDF 忠实转换为 Markdown，最大限度保留原文内容和结构 |
| **resume-reviewing** | 简历审核与优化建议（需根据个人情况修改 SKILL.md 中的背景信息） |
| **skill-rename** | 安全地为 skill 改名，自动更新所有依赖引用 |

## 安装方式

将需要的 skill 目录复制到 `~/.claude/skills/` 下即可：

```bash
# 克隆仓库
git clone <repo-url> claude-skills

# 复制单个 skill
cp -r claude-skills/md-zh ~/.claude/skills/

# 或全部复制
cp -r claude-skills/*/ ~/.claude/skills/
```

Windows 用户：

```powershell
# 复制单个 skill
Copy-Item -Recurse claude-skills\md-zh $env:USERPROFILE\.claude\skills\

# 或全部复制
Get-ChildItem claude-skills -Directory | Copy-Item -Recurse -Destination $env:USERPROFILE\.claude\skills\
```

## 依赖关系

```
md-fmt
├── md-zh      （排版规范化）
└── md-img-local（图片本地化）
```

- `md-fmt` 依赖 `md-zh` 和 `md-img-local`，使用 `md-fmt` 前需同时安装这两个 skill
- 其他 skill 可独立使用

## 开发设置

克隆后启用 pre-commit hook（防止个人敏感信息意外提交）：

```bash
git config core.hooksPath .githooks
cp .githooks/sensitive-patterns.example .githooks/sensitive-patterns
# 编辑 sensitive-patterns，填入你的个人信息模式
```

## 使用注意

- **resume-reviewing**：SKILL.md 中包含个人求职背景信息，使用前请根据自己情况修改
