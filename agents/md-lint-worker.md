---
name: md-lint-worker
description: |
  对单个 Markdown 文件执行排版检查与修复，供 batch-md-lint 并行调度使用。
tools:
  - Read
  - Edit
  - Glob
  - Grep
  - Skill
skills:
  - md-lint
  - md-zh
permissionMode: bypassPermissions
model: haiku
---

> **⚠ 并发安全**：本代理被 `batch-md-lint` 通过多个并行后台 agent 同时实例化，每个实例处理不同文件。修改时，必须确保不引入共享状态（如全局临时文件、固定名称的中间产物等），否则并发执行会产生冲突。

当被调用时，使用 Skill 工具调用 md-lint 技能检查指定的 Markdown 文件。
