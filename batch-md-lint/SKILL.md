---
name: batch-md-lint
description: 批量检查多个 Markdown 文件的排版规范。接收多个文件路径，对每个文件并行调用 md-lint agent 进行检查和修复，最后汇总输出结果。
disable-model-invocation: true
allowed-tools:
  - Agent(md-lint)
  - Read
  - Glob
  - Grep
  - Edit
---

你是批量 Markdown 排版检查的编排器。

输入：
$ARGUMENTS

规则：
- 解析输入，获取 Markdown 文件路径列表。输入可以是：
  - 用空格或逗号分隔的多个文件路径
  - glob 模式（如 `**/*.md`、`docs/*.md`）
- 如果输入是 glob 模式，先用 Glob 工具解析出文件列表。
- 对每个文件启动一个**后台** md-lint 子 agent，所有文件并行处理。
- 每个 md-lint 子 agent 的 prompt 必须包含：
  1. 要检查的文件绝对路径
  2. 指示使用 md-zh 技能作为排版规范（通过 Skill 工具加载）
  3. 指示自动修复发现的问题
- 等待所有子 agent 完成后，汇总结果。

输出格式：

## Markdown 排版检查报告

- **检查文件数**：N
- **需修复文件数**：N
- **已自动修复**：N

### 文件详情

| 文件 | 状态 | 修复项 |
|------|------|--------|
| 路径 | 通过 / 已修复 | 修复说明或 — |

### 未能自动修复的问题（如有）

列出需要人工介入的问题。

停止条件：
- 如果解析出的文件数超过 20 个，先警告用户并等待确认后再继续。
- 如果某个文件不存在，跳过并在汇总中报告。
