---
name: cc-adv-guide
description: |
  【知识库】Claude Code 进阶指南，包含 Skills 与 Agents 的高级用法和设计模式。
  当大模型需要创建或回答 skills、agents 相关内容时启用。
type: knowledge
---

# Claude Code 进阶指南：Skills 与 Agents

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

**实测验证**：`batch-md-fmt-v2` 曾尝试用"通用 agent + `mode: bypassPermissions`"替代 worker agent 方案，结果后台 agent 中的 `md-lint` Skill 调用仍被拒绝。`bypassPermissions` 仅影响文件编辑等常规工具的权限提示，对 Skill 工具无效。

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
