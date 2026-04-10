\# 个人偏好



\## 沟通方式

\- 使用中文回复



\## 通用代码风格

\- 缩进使用 4 空格

\## 记录知识点的规则

\- 当用户要求"记录"某个知识点时：
  \- **Claude Code 相关内容** → 写入 `E:\work\blog\ai\claude-code\tips.md`
  \- **其他内容** → 先询问用户写入位置（某个具体文件、项目记忆、还是全局记忆）

\## 创建技能的规则

\- 创建新的文件处理类技能时，主动询问用户是否需要支持批量（多文件）执行
\- 如果需要批量支持，先读取 `~/.claude/skills/batch-skill-pattern/SKILL.md`，按照其中的三层架构设计模式来实现
\- 后台 agent 的 `permissionMode` 必须写在 agent 定义文件（`~/.claude/agents/*.md`）的 frontmatter 中，调用时通过 `mode` 参数传入无效
