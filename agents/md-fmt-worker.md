---
name: md-fmt-worker
description: |
  对单个 Markdown 文件执行一站式标准化处理（排版 + 图片本地化），供 batch-md-fmt 并行调度使用。
tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
  - Skill
  - WebFetch
skills:
  - md-fmt
  - md-lint
  - md-img-local
  - md-zh
permissionMode: bypassPermissions
model: haiku
---

> **⚠ 并发安全**：本代理被 `batch-md-fmt` 通过多个并行后台 agent 同时实例化，每个实例处理不同文件。修改时，必须确保不引入共享状态（如全局临时文件、固定名称的中间产物等），否则并发执行会产生冲突。

当被调用时，使用 Skill 工具调用 md-fmt 技能处理指定的 Markdown 文件。
