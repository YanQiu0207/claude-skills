# Agent 定义文件完整参考

> 信息来源：[官方文档 - Create custom subagents](https://code.claude.com/docs/en/sub-agents)、[Agent SDK - Subagents](https://code.claude.com/docs/en/sdk/subagents)、[Agent SDK TypeScript 参考](https://code.claude.com/docs/en/agent-sdk/typescript)

## 文件结构

Agent 定义文件是 `.md` 文件，由 YAML frontmatter 和 Markdown 正文（系统提示词）组成：

```markdown
---
name: my-agent
description: 描述何时使用此 agent
tools: Read, Grep, Glob, Bash
model: sonnet
---

这里是系统提示词（Markdown 格式）。
subagent 只接收这个系统提示词（加上基本环境信息如工作目录），
不会接收完整的 Claude Code 系统提示词。
```

## 存储位置与优先级

| 优先级 | 位置 | 作用域 |
|--------|------|--------|
| 1（最高）| Managed settings | 组织级 |
| 2 | `--agents` CLI 标志 | 当前会话 |
| 3 | `.claude/agents/` | 当前项目 |
| 4 | `~/.claude/agents/` | 用户级（所有项目）|
| 5（最低）| Plugin 的 `agents/` 目录 | Plugin 启用的项目 |

同名 subagent 按优先级覆盖。Plugin subagent 出于安全原因**不支持** `hooks`、`mcpServers` 和 `permissionMode` 字段。

---

## Frontmatter 字段速查

### 核心字段

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `string` | 是 | - | 唯一标识符，使用小写字母和连字符（如 `code-reviewer`）|
| `description` | `string` | 是 | - | 描述何时应委派任务给此 subagent。Claude 根据此字段决定是否自动委托任务 |

### 工具与权限

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `tools` | `string`（逗号分隔）或 `string[]` | 否 | 继承所有工具 | 允许使用的工具白名单。支持 `Agent(worker, researcher)` 语法限制可派生的 subagent 类型 |
| `disallowedTools` | `string`（逗号分隔）或 `string[]` | 否 | - | 禁止使用的工具黑名单。若与 `tools` 同时设置，`disallowedTools` 先执行 |
| `permissionMode` | `string` | 否 | `default` | 权限模式，见下方详细说明 |

**`permissionMode` 可选值：**

| 值 | 说明 |
|----|------|
| `default` | 标准权限检查，需要用户确认 |
| `acceptEdits` | 自动批准文件编辑 |
| `auto` | 后台分类器审查工具调用 |
| `dontAsk` | 自动拒绝所有权限提示 |
| `bypassPermissions` | 跳过所有权限提示（后台 agent 必须使用此模式）|
| `plan` | 只读探索模式 |

### 模型与资源

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `model` | `string` | 否 | `inherit` | 使用的模型。可选：`sonnet`、`opus`、`haiku`、完整模型 ID（如 `claude-opus-4-6`）或 `inherit`（继承主会话模型）|
| `effort` | `string` | 否 | 继承会话级别 | 思考 effort level：`low`、`medium`、`high`、`max`（`max` 仅限 Opus 4.6）|
| `maxTurns` | `number` | 否 | 无限制 | 最大 agentic 回合数（API 往返次数），达到后 subagent 停止 |

**模型解析优先级：**

1. `CLAUDE_CODE_SUBAGENT_MODEL` 环境变量（若设置）
2. 调用时传入的 `model` 参数
3. subagent 定义文件中的 `model` frontmatter
4. 主会话的模型

### 依赖注入

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `skills` | `string[]` | 否 | - | 启动时注入到 subagent 上下文的 skill 列表。注入完整 skill 内容，而非仅使其可调用。subagent **不会**从父对话继承 skill |
| `mcpServers` | `(string \| object)[]` | 否 | - | 可用的 MCP 服务器。每个条目可以是已配置服务器的名称字符串，或内联定义（以服务器名为 key，完整 MCP 配置为 value）|

### 生命周期与行为

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `hooks` | `object` | 否 | - | 作用域限定在此 subagent 的生命周期钩子。支持 `PreToolUse`、`PostToolUse`、`Stop` 等事件 |
| `memory` | `string` | 否 | - | 持久记忆作用域：`user`（`~/.claude/agent-memory/<name>/`）、`project`（`.claude/agent-memory/<name>/`）或 `local`（`.claude/agent-memory-local/<name>/`）|
| `background` | `boolean` | 否 | `false` | 设为 `true` 时，此 subagent 始终作为后台任务运行 |
| `isolation` | `string` | 否 | - | 设为 `worktree` 时在临时 git worktree 中运行，提供隔离的仓库副本。若 subagent 未做任何更改，worktree 自动清理 |
| `initialPrompt` | `string` | 否 | - | 当此 agent 作为主会话 agent 运行时（通过 `--agent` 或 `agent` 设置），自动作为第一个用户回合提交。支持处理命令和 skill。会前置到用户提供的任何 prompt 之前 |

### 显示

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `color` | `string` | 否 | - | 在任务列表和 transcript 中的显示颜色。可选：`red`、`blue`、`green`、`yellow`、`purple`、`orange`、`pink`、`cyan` |

### 路径约束（实验性）

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `allowedProjectGlobs` | `string[]` | 否 | - | glob 模式数组，限定此 agent 可操作的项目路径 |
| `disallowedProjectGlobs` | `string[]` | 否 | - | glob 模式数组，排除此 agent 不可操作的项目路径，优先于 `allowedProjectGlobs` |

> 注意：路径约束字段出现在 [GitHub Issue #18784](https://github.com/anthropics/claude-code/issues/18784)，在代码中被解析但行为可能不稳定。

---

## 最佳实践

### 1. 职责单一

一个 subagent 只做一件事。避免创建"万能 agent"。

### 2. 写好 description

Claude 根据 description 决定何时自动委派任务。包含 "use proactively" 等短语可鼓励主动委派：

```yaml
description: Expert code review specialist. Use proactively after writing or modifying code.
```

### 3. 最小化工具权限

只授予 agent 完成任务所需的工具，提高安全性和专注度：

```yaml
# 只读审查 agent —— 不需要 Edit 和 Write
tools: Read, Grep, Glob, Bash
```

### 4. 用 `tools` 的 `Agent()` 语法限制可派生 subagent

```yaml
# 只能派生 worker 和 researcher 两种 subagent
tools: Agent(worker, researcher), Read, Bash
```

### 5. 用 `model` 控制成本

- 探索类 / 简单任务：`haiku`（快且便宜）
- 中等复杂度：`sonnet`
- 复杂分析 / 关键决策：`opus`

### 6. 后台 agent 必须设置 `permissionMode: bypassPermissions`

后台 agent 无法与用户交互，若触发权限提示会阻塞。

### 7. 显式声明 `skills` 依赖

subagent 不继承父对话的 skill。必须在 `skills` 字段中列出所有需要的 skill，**包括下游 skill 的依赖**：

```yaml
skills:
  - md-fmt        # 执行层 skill
  - md-lint       # md-fmt 调用的下游 skill
  - md-img-local  # md-fmt 调用的下游 skill
  - md-zh         # md-lint 调用的下游 skill
```

### 8. 利用 `memory` 积累知识

推荐 `project` 作用域，可通过版本控制共享。在 prompt 中加入更新记忆的指示：

```
Update your agent memory as you discover codepaths, patterns, and important context.
```

### 9. 将项目级 subagent 纳入版本控制

`.claude/agents/` 中的定义文件应提交到 Git，方便团队共享和协作改进。

### 10. 隔离高容量操作

运行测试、获取文档、处理日志等会产生大量输出的操作，委派给 subagent 可保持主对话上下文清洁。

---

## 官方示例

### 示例 1：Code Reviewer（只读审查）

```markdown
---
name: code-reviewer
description: Expert code review specialist. Proactively reviews code for quality, security, and maintainability. Use immediately after writing or modifying code.
tools: Read, Grep, Glob, Bash
model: inherit
---

You are a senior code reviewer ensuring high standards of code quality and security.

When invoked:
1. Run git diff to see recent changes
2. Focus on modified files
3. Begin review immediately

Review checklist:
- Code is clear and readable
- Functions and variables are well-named
- No duplicated code
- Proper error handling
- No exposed secrets or API keys
- Input validation implemented
- Good test coverage
- Performance considerations addressed

Provide feedback organized by priority:
- Critical issues (must fix)
- Warnings (should fix)
- Suggestions (consider improving)

Include specific examples of how to fix issues.
```

**要点**：`tools` 中没有 `Edit` 和 `Write`，确保只读审查。

### 示例 2：Debugger（可修改代码）

```markdown
---
name: debugger
description: Debugging specialist for errors, test failures, and unexpected behavior. Use proactively when encountering any issues.
tools: Read, Edit, Bash, Grep, Glob
---

You are an expert debugger specializing in root cause analysis.

When invoked:
1. Capture error message and stack trace
2. Identify reproduction steps
3. Isolate the failure location
4. Implement minimal fix
5. Verify solution works

For each issue, provide:
- Root cause explanation
- Evidence supporting the diagnosis
- Specific code fix
- Testing approach
- Prevention recommendations

Focus on fixing the underlying issue, not the symptoms.
```

**要点**：包含 `Edit` 工具，允许修复代码。prompt 强调流程化的根因分析。

### 示例 3：Data Scientist（领域专用 + 模型控制）

```markdown
---
name: data-scientist
description: Data analysis expert for SQL queries, BigQuery operations, and data insights. Use proactively for data analysis tasks and queries.
tools: Bash, Read, Write
model: sonnet
---

You are a data scientist specializing in SQL and BigQuery analysis.

When invoked:
1. Understand the data analysis requirement
2. Write efficient SQL queries
3. Use BigQuery command line tools (bq) when appropriate
4. Analyze and summarize results
5. Present findings clearly

Always ensure queries are efficient and cost-effective.
```

**要点**：`model: sonnet` 控制成本，`tools` 精确限定为数据分析所需。

### 示例 4：Database Reader（带 Hook 的条件验证）

```markdown
---
name: db-reader
description: Execute read-only database queries. Use when analyzing data or generating reports.
tools: Bash
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-readonly-query.sh"
---

You are a database analyst with read-only access. Execute SELECT queries to answer questions about the data.

You cannot modify data. If asked to INSERT, UPDATE, DELETE, or modify schema, explain that you only have read access.
```

**要点**：`hooks.PreToolUse` 在每次 Bash 调用前运行验证脚本，确保只执行只读查询。双重保障（prompt 约束 + hook 验证）。

### 示例 5：Browser Tester（MCP 服务器集成）

```markdown
---
name: browser-tester
description: Tests features in a real browser using Playwright
mcpServers:
  - playwright:
      type: stdio
      command: npx
      args: ["-y", "@playwright/mcp@latest"]
  - github
---

Use the Playwright tools to navigate, screenshot, and interact with pages.
```

**要点**：`mcpServers` 支持两种格式——内联定义（playwright）和引用已配置的服务器名（github）。

### 示例 6：Coordinator（限制可派生 subagent）

```markdown
---
name: coordinator
description: Coordinates work across specialized agents
tools: Agent(worker, researcher), Read, Bash
---

You are a coordinator that delegates tasks to specialized agents.
Analyze the task, break it down, and delegate to the appropriate agent:
- worker: for implementation tasks
- researcher: for information gathering
```

**要点**：`Agent(worker, researcher)` 语法限制只能派生这两种 subagent，防止无限制的 agent 调用链。

### 示例 7：Memory-enabled Agent（持久记忆）

```markdown
---
name: codebase-explorer
description: Explores and documents codebase architecture
tools: Read, Grep, Glob, Bash
memory: project
---

You are a codebase exploration specialist. Discover and document architecture, patterns, and conventions.

Update your agent memory as you discover:
- Important codepaths and their purposes
- Architectural patterns and conventions
- Key configuration files and their roles
- Testing patterns and coverage gaps

Check your memory first before re-exploring areas you've already documented.
```

**要点**：`memory: project` 让 agent 在 `.claude/agent-memory/codebase-explorer/` 中积累知识，跨会话持久化。

---

## 关键限制

- **subagent 不能嵌套派生其他 subagent**：subagent 内部调用 Agent 工具不被支持
- **subagent 启动时加载**：手动新增定义文件后需重启会话或用 `/agents` 重新加载
- **后台 subagent 无法向用户提问**：`AskUserQuestion` 工具调用会失败，但 subagent 会继续运行
- **Windows 上长 prompt 可能失败**：受命令行长度限制（8191 字符）
- **Plugin subagent 不支持** `hooks`、`mcpServers`、`permissionMode` 字段
