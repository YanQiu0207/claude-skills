---
name: cc-adv-guide
description: |
  【知识库】Claude Code 进阶指南，包含 Skills 与 Agents 的高级用法和设计模式。
  当大模型需要创建或回答 skills、agents 相关内容时启用。
user-invocable: false
---

# Claude Code 进阶指南

> **维护规则**：保持本文件简洁。大段参考数据应放在 `reference/` 目录下的独立文件中，SKILL.md 中仅保留摘要并注明"当需要了解 XX 时，请读取 [reference/xxx.md]"。本文件的定位是索引 + 核心经验，不是百科全书。
>
> **写入审查**：每次向本文件写入新内容前，必须检查：（1）该知识是否有写入的必要（能从代码/文档直接推导的不写）；（2）是否与已有内容重复（重复则合并或更新，不新增）；（3）是否与已有内容冲突（冲突时需找用户确认保留哪个）。

---

## Skill `allowed-tools` 与 Agent `tools` 对比

两者都用于控制工具，但解决的问题层次不同：

| 维度 | Skill `allowed-tools` | Agent `tools` |
|------|----------------------|---------------|
| **本质** | 权限预批准（免提示） | 能力白名单（隔离） |
| **未列出的工具** | 仍可用，需用户批准 | 完全不可用 |
| **粒度** | 支持参数模式，如 `Bash(git *)` | 同样支持，如 `Bash(npm test *)` |
| **默认行为** | 无预批准 | 省略则继承所有工具 |
| **生效范围** | 技能激活期间 | 整个 agent 生命周期 |
| **互补机制** | 无 | `disallowedTools` 黑名单（优先级高于 `tools`） |

**一句话总结**：`allowed-tools` 是"这些工具不用问我"，`tools` 是"你只能用这些工具"。

各字段的完整说明分别在 [reference/skill-guide.md](reference/skill-guide.md)（`allowed-tools` 字段）和 [reference/agent-guide.md](reference/agent-guide.md)（`tools` / `disallowedTools` 字段）中。

---

## Agent 工具参数速查

调用 Agent 工具时可设置的参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | string（必填）| 任务描述 |
| `prompt` | string（必填）| 任务内容，subagent 是独立上下文，需包含完整信息（文件绝对路径等） |
| `subagent_type` | string | 指定 Agent 类型，如 `"md-fmt-worker"` |
| `mode` | string | 权限模式：`"bypassPermissions"` / `"auto"` / `"acceptEdits"` 等 |
| `model` | string | 覆盖模型：`"haiku"` / `"sonnet"` / `"opus"` |
| `name` | string | 命名，便于后续用 SendMessage 寻址 |
| `run_in_background` | bool | 后台异步执行，完成后通过 task-notification 通知 |
| `isolation` | string | 隔离模式：`"worktree"` 在独立 git worktree 中运行 |

---

## Agent 定义的两种运行模式与嵌套限制

同一个 agent 定义文件可以在两种模式下运行，能力不同：

| 运行模式 | 启动方式 | 身份 | 能否调用 Agent 工具 |
|---------|---------|------|-------------------|
| **主线程模式** | `claude --agent coordinator` | 主线程本身 | 能 |
| **subagent 模式** | @mention、Agent 工具派生 | subagent | **不能** |

### 嵌套限制

**Subagent 不能派生其他 subagent。** `Agent()` 语法写在 subagent 定义中无效。需要嵌套委托时，用 Skill 或从主对话链式调用 subagent。

```
主线程（默认 Claude 或 --agent 启动的 agent）
  └─ 可调用 Agent 工具派生 subagent ✅
        └─ 不能再调用 Agent 工具 ❌
```

### `Agent()` 语法的适用范围

`tools` 字段中的 `Agent(worker, researcher)` 语法**仅在主线程模式下生效**——限制该主线程可以派生哪些 subagent 类型：

```yaml
# coordinator 定义，通过 claude --agent coordinator 启动时生效
tools: Agent(worker, researcher), Read, Bash
```

- 省略 `Agent`：主线程不能派生任何 subagent
- `Agent`（无括号）：可派生任意 subagent
- `Agent(a, b)`：只能派生 `a` 和 `b`

### 用户调用 agent 的三种方式

| 方式 | 示例 | 说明 |
|------|------|------|
| 自然语言 | `用 code-reviewer 看一下` | Claude 自行判断是否委托 |
| @-mention | `@"code-reviewer (agent)" 审查认证模块` | 保证该 agent 运行 |
| `--agent` | `claude --agent coordinator` | 整个会话以该 agent 身份运行（主线程模式） |

前两种方式中，agent 作为 **subagent** 运行；第三种方式中，agent 作为**主线程**运行，具备派生 subagent 的能力。

---

## 后台 Agent 调用 Skill 的权限问题

### 问题现象

用 `mode: "bypassPermissions"` 启动后台 Agent，让它调用 Skill（如 `md-fmt`），Skill 内部再调用下游 Skill（如 `md-lint`）时，下游 Skill 调用被拒绝：

```
md-lint 技能调用被拒绝了。这是因为当前是在后台 agent 上下文中运行，权限受到限制。
```

### 根本原因

**`mode: "bypassPermissions"` 不等于 agent 定义中的 `permissionMode: bypassPermissions`。**

更关键的是 agent 定义中的 `skills` 字段：

```yaml
# agents/xxx-worker.md
skills:
  - md-fmt
  - md-lint      # ← 必须显式声明所有下游依赖
  - md-img-local
permissionMode: bypassPermissions
```

当 skills 在 agent 定义层预加载时，后台 agent 内的嵌套 Skill 调用才能可靠工作。仅靠 `mode: "bypassPermissions"` 无法保证这一点。

### 解决方案

使用 `subagent_type` 指向已配置好的 worker agent，而不是用通用 agent + mode 参数：

```javascript
// ❌ 不可靠：通用 agent + mode 参数（即使加了 bypassPermissions 也无效）
Agent({
  mode: "bypassPermissions",
  prompt: "调用 md-fmt 技能..."
})

// ✅ 正确：指向预配置的 worker agent
Agent({
  subagent_type: "md-fmt-worker",  // 已内置 permissionMode + skills 依赖
  run_in_background: true,
  prompt: "调用 md-fmt 技能处理 /absolute/path/file.md"
})
```

**实测验证**：`batch-md-fmt-v2` 曾尝试用"通用 agent + `mode: bypassPermissions`"替代 worker agent 方案，结果：

- **Skill 工具**：后台 agent 中的 `md-lint` Skill 调用被拒绝
- **Bash 工具**：即使只是执行 `curl` 下载图片，agent 同样无法自动获得权限，转而向用户请求授权——而后台 agent 无法与用户交互，等同于阻塞

`mode: "bypassPermissions"` 的实际效果**比文档描述的更窄**：它对 Skill 工具和 Bash 工具均无效，不能可靠地用于需要这两类工具的后台任务。

### 无 worker agent 时的降级方案

如果 worker agent 尚未创建，唯一可靠的兜底方式是**在主对话上下文中直接调用 Skill**，但这会丧失批量并行能力，退化为串行处理。

---

## Skill 批量执行三层设计模式

当一个 skill 需要支持批量（多文件）执行时，采用三层架构：

```
batch-xxx（skill）──调度层
  └─ xxx-worker（agent）──配置层
       └─ xxx（skill）──执行层
```

### 各层职责

| 层级 | 类型 | 职责 |
|------|------|------|
| **调度层** `batch-xxx` | Skill | 文件列表展开（Glob）、并行分发 Agent、汇总报告 |
| **配置层** `xxx-worker` | Agent | 声明 `permissionMode`、`skills` 依赖和工具白名单，作为调度层与执行层的桥梁 |
| **执行层** `xxx` | Skill | 单文件的实际处理逻辑 |

调度层和执行层分离的好处：单文件 skill 可独立使用，批量 skill 只负责编排，不重复业务逻辑。

### 为什么需要配置层

后台 Agent 需要通过 agent 定义文件提供以下配置，才能可靠地并行调用 skill：

- **`permissionMode: bypassPermissions`**：后台 agent 无法与用户交互，必须跳过权限确认
- **`skills`**：明确声明可用的 skill 依赖，确保后台 agent 能加载和调用目标 skill（包括执行层 skill 内部调用的所有下游 skill）
- **`subagent_type` 路由**：调度层通过 `subagent_type: "xxx-worker"` 指定 agent 类型，系统能正确路由到配置好的 worker agent

### 调度层模板（`batch-xxx/SKILL.md`）

核心流程：

1. **确定文件列表**：Glob 展开通配符，或逐个确认路径存在
2. **并行分发**：在同一条消息中发起多个 Agent 调用
   - `subagent_type: "xxx-worker"`
   - `run_in_background: true`
   - prompt 中写明文件**绝对路径**和要调用的**技能名称**（subagent 是独立上下文，看不到主对话）
   - 同时并行不超过 8 个，超过时分批
   - **关键**：所有 Agent 调用必须在一条消息中发出，不能逐个发送
3. **汇总报告**：所有 agent 返回后，用表格汇总结果

Agent 调用示例：

```javascript
Agent({
  description: "xxx: file1.md",
  subagent_type: "xxx-worker",
  run_in_background: true,
  prompt: "请使用 Skill 工具调用 xxx 技能，对文件 /absolute/path/to/file1.md 执行处理。"
})
```

### 配置层模板（`agents/xxx-worker.md`）

```yaml
---
name: xxx-worker
description: |
  对单个文件执行 xxx 处理，供 batch-xxx 并行调度使用。
tools:
  - Read
  - Edit
  - Skill
  # 根据执行层 skill 需要的工具添加
skills:
  - xxx
  # 如果执行层 skill 会调用其他 skill，也需要在此声明
permissionMode: bypassPermissions
---

> **⚠ 并发安全**：本代理被 `batch-xxx` 通过多个并行后台 agent 同时实例化，每个实例处理不同文件。修改时，必须确保不引入共享状态（如全局临时文件、固定名称的中间产物等），否则并发执行会产生冲突。

当被调用时，使用 Skill 工具调用 xxx 技能处理指定的文件。
```

关键字段说明：

- **`skills`**：必须声明执行层 skill 及其**所有下游 skill** 的依赖（这是后台 Skill 调用能否成功的关键）
- **`permissionMode: bypassPermissions`**：后台 agent 无法与用户交互，需跳过权限确认
- **`tools`**：需包含执行层 skill 所需的所有工具

### 并发安全

执行层 skill 必须确保并发安全：

- 不使用固定名称的临时文件（用 `mktemp` 或 PID 后缀）
- 不依赖共享的全局状态
- 每个文件的产出路径互不冲突（如用文件名前缀区分）

**需要标注并发安全说明的层级**（在 frontmatter 之后、正文开头）：

| 层级 | 文件位置 |
|------|----------|
| 配置层 agent | `agents/xxx-worker.md` |
| 执行层 skill | `skills/xxx/SKILL.md` |
| 执行层下游 skill | 如 `md-img-local` |

标注格式：

```markdown
> **⚠ 并发安全**：本技能/代理被 `batch-xxx` 通过多个并行后台 agent 同时调用，每个 agent 处理不同文件。修改时，必须确保不引入共享状态（如全局临时文件、固定名称的中间产物等），否则并发执行会产生冲突。
```

调度层 `batch-xxx` 本身不需要标注（它是调度方，不会被并发调用）。

### 实际案例

`batch-md-fmt`（调度层）→ `md-fmt-worker`（配置层）→ `md-fmt`（执行层）→ `md-img-local`（下游 skill）

---

## 通用 skill-runner Agent：配置层的替代方案

### 问题

三层设计模式中，每个 skill 的配置层 worker agent 没有业务逻辑，只是"权限 + 技能声明的壳"。每新增一个需要批量执行的 skill，就要再写一个几乎相同的 worker agent，形成样板代码。

### 思路

创建一个通用的 `skill-runner` agent，在 `skills` 字段中声明**所有**可执行类 skill 及其下游依赖，使任何调度层都能用 `subagent_type: "skill-runner"` 统一调用，无需再为每个 skill 单独创建 worker。

```
batch-xxx（skill）──调度层
  └─ skill-runner（agent）──通用配置层（替代 xxx-worker）
       └─ xxx（skill）──执行层
```

### 关键权衡：上下文开销

agent 的 `skills` 字段会把**完整 skill 内容**注入 subagent 上下文。通用 agent 需要加载所有 skill，即使每次只用其中一个：

- **专用 worker**：只注入相关 skill（如 `md-lint-worker` 仅 ~7.5KB）
- **通用 skill-runner**：注入所有 skill（随 skill 数量增长，可达数十 KB）

| 影响维度 | 说明 |
|---------|------|
| 模型选择 | `haiku` 对大量上下文敏感，通用 agent 建议默认 `sonnet`，成本高于 haiku |
| 扩展性 | skill 越多，每次调用的上下文浪费越大 |
| 准确性 | 多个 skill 定义同时加载，模型需从 prompt 判断调用哪个——实际影响较小，因为 prompt 会明确指定 |

### 适用场景判断

| 场景 | 推荐方案 |
|------|---------|
| 高频批量调用、对成本/延迟敏感 | **专用 worker**（最小上下文，可用 haiku） |
| skill 数量多但批量调用不频繁 | **通用 skill-runner**（减少样板，可接受 sonnet 成本） |
| 快速原型验证 | **通用 skill-runner**（一个 agent 走天下） |

### 模板

```yaml
---
name: skill-runner
description: |
  通用技能执行器，供批量调度层并行调用。
  可执行任何已注册的 skill，无需为每个 skill 单独创建 worker agent。
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
  # 所有可执行类 skill 及其下游依赖（排除调度层 batch-* 和纯知识库）
  - skill-a
  - skill-b
  - skill-b-downstream-dep
permissionMode: bypassPermissions
model: sonnet
---

当被调用时，根据 prompt 中的指令使用 Skill 工具调用指定的技能。
```

**维护要点**：新增 skill 后需同步更新 `skills` 列表，否则后台调用会因 skill 未注入而失败。

调用方式：

```javascript
Agent({
  subagent_type: "skill-runner",
  model: "haiku",                 // 可按需覆盖默认模型
  run_in_background: true,
  prompt: "使用 Skill 工具调用 xxx 技能处理 /absolute/path/to/file.md"
})
```

---

## Skill 与 Agent 执行时的权限架构总览

Skill 的权限不是单独一套沙箱，而是叠在 Claude Code 的权限系统之上。整体分为 4 层：

### 层级概览

| 层级 | 控制什么 | 机制 |
|------|---------|------|
| 调用控制 | skill 能否被触发 | `disable-model-invocation` / `user-invocable` |
| 工具预授权 | skill 激活后哪些工具免确认 | `allowed-tools`（详见上方对比表） |
| 全局权限规则 | 工具调用的最终裁决 | `permissions.deny/ask/allow`（settings.json） |
| Agent 权限 | subagent 中的工具与 skill 可用性 | `tools` / `skills` / `permissionMode` |

### 关键规则

1. **deny 永远优先于 allow**：权限判断顺序是 deny → ask → allow，第一个匹配的规则生效。无法通过"deny 全部 + allow 白名单"实现选择性放行
2. **`allowed-tools` 是"额外放行器"，不是"限制器"**：未列出的工具仍可用，只是需要用户确认
3. **subagent 不继承父对话的 skills**：必须在 agent 定义中通过 `skills` 字段显式声明所有依赖（包括下游 skill）
4. **内置 agent 有预定义的工具集**：Explore/Plan 禁止 Edit/Write（只读），general-purpose 拥有全部工具。不是从父对话"继承"

### 配置来源优先级

1. **Managed**（企业/IT 下发）— 无法被任何其他层级覆盖
2. **命令行参数** — 临时会话覆盖
3. **本地项目**（`.claude/settings.local.json`）
4. **项目共享**（`.claude/settings.json`）
5. **用户配置**（`~/.claude/settings.json`）

`allowManagedPermissionRulesOnly: true`（仅限 managed settings 设置）可禁止用户和项目自定义权限规则。

### 实用做法

- 危险 skill 加 `disable-model-invocation: true`，防止模型自动触发
- 知识类 skill 设 `user-invocable: false`
- 后台 agent 调用 skill 时，在 agent 定义中通过 `skills` 声明所有依赖，并设置 `permissionMode: bypassPermissions`
- skill 调用链上每层都需有完整的 `allowed-tools` 声明（详见"后台 Agent 调用 Skill 的权限问题"一节）

---

## 创建技能的快速参考

创建新技能时直接参考此节，无需每次去读取现有技能来了解结构。

### 文件结构

```
~/.claude/skills/<name>/
├── SKILL.md              # 必需 - 核心定义（frontmatter + 指令）
├── reference/            # 可选 - 详细参考文档（按需读取，减少 token）
│   └── xxx.md
└── scripts/              # 可选 - 辅助脚本
    └── helper.py
```

### SKILL.md 模板

```yaml
---
name: skill-name
description: |
  一句话说明做什么。何时使用的触发条件描述。
  补充说明（多行时用 | 管道符）。
argument-hint: "[参数提示]"
disable-model-invocation: true    # 仅手动调用时加
user-invocable: false             # 仅知识库类 skill 加
allowed-tools:                    # 预授权工具列表（可选）
  - Read
  - Edit
  - Bash
model: sonnet                     # 可选：haiku / sonnet / opus
---

当此 skill 生效时，回答第一行固定写：Using skill: skill-name

## 输入

描述用户需要提供什么参数。

## 处理流程

### 1. 步骤一

...

### 2. 步骤二

...

## 输出格式

描述输出的结构和样式。

## 边界情况

列出需要特殊处理的场景。
```

### 常用 frontmatter 字段速查

| 字段 | 用途 | 常见值 |
|------|------|--------|
| `name` | 技能名，即 `/slash-command` 名 | 小写字母、数字、连字符 |
| `description` | Claude 用来判断是否自动激活 | 前 250 字符最关键 |
| `argument-hint` | 自动补全时的参数提示 | `"[filename]"`、`"write <name> \| list"` |
| `disable-model-invocation` | 禁止 Claude 自动调用 | `true`（有副作用的操作） |
| `user-invocable` | 从 `/` 菜单隐藏 | `false`（知识库类） |
| `allowed-tools` | 预授权工具（免确认） | 列表或空格分隔字符串 |
| `model` | 模型覆盖 | `haiku` / `sonnet` / `opus` |
| `context` | 独立上下文运行 | `fork` |

完整字段说明见 [reference/skill-guide.md](reference/skill-guide.md)。

### 批量支持决策

创建**文件处理类**技能时，先询问用户是否需要支持批量（多文件）执行：

- 需要批量支持 → 按本文档"Skill 批量执行三层设计模式"实现
- 不需要 → 只创建单文件 skill 即可

### 设计要点

- **正文保持 500 行以内**，详细参考移到 `reference/` 子目录
- **description 结构**：[做什么] + [何时使用] + [能力]，前 250 字符放关键信息
- **处理流程用编号步骤**，让模型严格按顺序执行
- **输出格式用代码块给出模板**，确保格式一致
- **边界情况显式列出**，避免模型自行推断

---

## Skill 字段参考与官方最佳实践

当需要了解以下内容时，请读取 [reference/skill-guide.md](reference/skill-guide.md)：

- Skill YAML frontmatter 的完整字段列表及各字段含义
- 字符串替换变量（`$ARGUMENTS`、`${CLAUDE_SKILL_DIR}` 等）
- 调用控制（`disable-model-invocation` / `user-invocable` 的组合效果）
- 动态上下文注入（`!command` 语法）
- description 写法、文件组织、渐进式披露等最佳实践
- 官方示例（参考知识类、手动触发、工具预授权、子代理 fork、位置参数、脚本捆绑等）
- 技能存放位置与优先级规则

## Agent 定义文件参考与官方最佳实践

当需要了解以下内容时，请读取 [reference/agent-guide.md](reference/agent-guide.md)：

- Agent `.md` 文件的完整 frontmatter 字段列表及各字段含义（`name`、`description`、`tools`、`model`、`permissionMode`、`skills`、`hooks`、`mcpServers`、`memory` 等）
- 工具权限控制（`tools` 白名单、`disallowedTools` 黑名单、`Agent()` 语法限制可派生 subagent）
- 模型选择与解析优先级
- 依赖注入（`skills`、`mcpServers`）
- 生命周期与行为控制（`hooks`、`memory`、`background`、`isolation`、`initialPrompt`）
- 存储位置与优先级规则
- 官方最佳实践（职责单一、最小权限、description 写法、成本控制等）
- 官方示例（只读审查、调试修复、领域专用、Hook 验证、MCP 集成、Coordinator、持久记忆等 7 个完整示例）
- 关键限制与注意事项
