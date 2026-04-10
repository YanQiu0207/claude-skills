\# 全局指令

\## 沟通方式
\- 使用中文回复

\## 通用代码风格
\- 缩进使用 4 空格

\## Claude Code 参考知识库
\- 参考文件：`~/.claude/claude_ref/claude-code-guide.md`
\- **查询时**：回答 Claude Code 相关问题时
  \- 模型自身有明确答案：直接回答；若此文件中缺少该内容，询问用户是否更新到此文件
  \- 模型自身没有明确答案：查阅此文件作为补充；若参考了此文件内容，要告知用户信息来源
\- **记录时**：当用户要求"记录"某个知识点时
  \- Claude Code 相关内容 → 写入此文件
  \- 其他内容 → 先询问用户写入位置（某个具体文件、项目记忆、还是全局记忆）

\## 中文 Markdown 排版规范
\- 参考文件：`~/.claude/claude_ref/markdown-zh.md`
\- 生成、审核或修改中文 Markdown 内容时，必须遵循此排版规范

\## 创建技能的规则
\- 创建新的文件处理类技能时，主动询问用户是否需要支持批量（多文件）执行
\- 如果需要批量支持，先读取 `~/.claude/claude_ref/claude-code-guide.md`，按照其中的三层架构设计模式来实现
\- 后台 agent 的 `permissionMode` 必须写在 agent 定义文件（`~/.claude/agents/*.md`）的 frontmatter 中
  \- 注意：调用时通过 `mode` 参数传入无效
