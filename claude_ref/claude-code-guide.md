# Claude Code 使用技巧

## 会话管理

### 恢复最近的会话

```bash
claude --continue
```

自动恢复最近一次的会话，包括完整的对话历史。

### 恢复指定会话

```bash
claude --continue <session-id>
```

### 列出所有会话

在 Claude Code 中输入：

```
/resume
```

不带任何参数时，会打开会话选择器，列出当前目录下所有可用的会话供你选择。也可以通过 `/resume <name 或 id>` 恢复指定会话。

### 分叉会话

```bash
claude --continue --fork-session
```

基于之前的对话创建一个新会话，原会话不受影响。适合从同一起点尝试不同方案。

### 其他会话相关命令

| 命令 | 说明 |
| --- | --- |
| `/rename [name]` | 给当前会话命名，方便后续查找 |
| `/branch` 或 `/fork` | 从当前对话创建一个分支 |
| `/stats` | 查看会话使用统计 |

### `/clear` 不会删除会话

`/clear` 只是清除当前上下文窗口中的对话内容，释放上下文空间。对话历史仍然保存在本地的 JSONL 文件中（`~/.claude/projects/` 目录下），不会删除任何数据。

执行过 `/clear` 后，仍然可以通过 `claude --continue <session-id>` 或 `/resume` 恢复完整的对话历史（包括 `/clear` 之前的内容）。

### 会话存储位置

所有会话数据保存在 `~/.claude/projects/` 目录下，以 JSONL 格式存储。如需永久删除会话，需手动删除对应文件。

> 注意：恢复会话时，之前授予的权限不会继承，需要重新授权。

## Plan 模式

进入 Plan 模式的两种方式：

1. **快捷键**：按 `Shift+Tab` 切换（再按一次切换回正常模式）
2. **输入提示词**：在消息中包含 "plan" 相关的词

Plan 模式下只进行研究和分析，不会修改任何文件，适合动手前先理清思路。

## Subagent（自定义子代理）

### 创建 Subagent

在项目的 `.claude/agents/` 目录下创建 Markdown 文件，例如 `.claude/agents/code-reviewer.md`：

```markdown
---
name: code-reviewer
description: 代码审查专家。审查代码的质量、安全性和可维护性
tools: Read, Grep, Glob, Bash
model: sonnet
---

你是一个资深代码审查员。

当被调用时：
1. 运行 git diff 查看最近的更改
2. 关注修改的文件
3. 提供具体、可执行的反馈
```

### 关键配置字段

| 字段 | 说明 |
| --- | --- |
| `name` | 唯一标识符 |
| `description` | 描述（Claude 据此决定何时自动委托任务） |
| `tools` | 允许使用的工具白名单 |
| `disallowedTools` | 禁用的工具黑名单 |
| `model` | 使用的模型：`opus`/`sonnet`/`haiku` |
| `maxTurns` | 最大回合数 |
| `isolation` | 设为 `worktree` 在独立 git worktree 中运行 |
| `memory` | 持久内存作用域：`user`/`project`/`local` |

### 调用方式

```bash
# 查看所有可用 subagent
claude agents

# 作为主线程启动
claude --agent code-reviewer

# 在对话中 @mention
@code-reviewer 审查这个文件
```

也可以在 `.claude/settings.json` 中设为项目默认 agent：

```json
{ "agent": "code-reviewer" }
```

### 作用域

| 位置 | 作用域 |
| --- | --- |
| `.claude/agents/` | 项目级（推荐） |
| `~/.claude/agents/` | 用户级（所有项目可用） |

### 关键配置：`permissionMode`

`permissionMode` 控制 subagent 的权限行为：

| 值 | 说明 |
| --- | --- |
| `default` | 每次工具调用都需用户确认 |
| `acceptEdits` | 自动批准文件编辑，其他需确认 |
| `bypassPermissions` | 跳过所有权限弹窗，自动执行 |

`permissionMode` 可以通过两种方式设置：

- **agent 定义文件的 frontmatter**：适用于有独立 agent 定义文件的场景

```yaml
---
name: my-worker
permissionMode: bypassPermissions
---
```

- **Agent 工具调用时的 `mode` 参数**：适用于不需要独立 agent 定义文件的场景

```
Agent({
  mode: "bypassPermissions",
  run_in_background: true,
  prompt: "..."
})
```

### 关键配置：Skill 的 `allowed-tools`

Skill 的 YAML frontmatter 中的 `allowed-tools` 字段声明该 skill 执行时哪些工具可免权限弹窗使用。这是**后台 agent 能否正常调用 skill 的关键**。

```yaml
---
name: md-img-local
allowed-tools:
  - Read
  - Edit
  - Bash
  - Grep
  - Glob
---
```

**与 `permissionMode` 的区别**：

| 机制 | 作用对象 | 场景 |
| --- | --- | --- |
| `permissionMode` | agent 自身 | 控制 agent 直接使用工具时的权限 |
| `allowed-tools` | skill | 控制 skill 被调用时内部工具的权限 |

**后台 agent 调用 skill 链时**，链路上每个 skill 都必须有完整的 `allowed-tools` 声明。例如 batch 技能 → md-fmt（需要 allowed-tools）→ md-img-local（也需要 allowed-tools），任何一层缺失都会导致后台 agent 因无法交互审批而失败。

### 关键配置：`skills`

subagent 需要调用 skill 时，必须在 agent 定义文件的 frontmatter 中通过 `skills` 字段声明依赖。未声明的 skill 无法使用。

```yaml
---
name: my-worker
tools:
  - Read
  - Edit
  - Skill
skills:
  - md-fmt
  - md-zh
---
```

### 两种运行模式与嵌套限制

同一个 agent 定义文件有两种运行模式，能力不同：

| 运行模式 | 启动方式 | 身份 | 能否派生 subagent |
| --- | --- | --- | --- |
| **主线程模式** | `claude --agent coordinator` | 主线程 | 能 |
| **subagent 模式** | @mention 或 Agent 工具派生 | subagent | **不能** |

**嵌套限制**：subagent 不能派生其他 subagent（内部调用 Agent 工具无效）。需要嵌套委托时，用 Skill 或从主对话链式调用 subagent。

**`Agent()` 语法**：`tools` 字段中的 `Agent(worker, researcher)` 语法仅在主线程模式下生效，用于限制可派生的 subagent 类型。写在 subagent 定义中无效。

### 最佳实践

- **一个 subagent 只做一件事**，保持职责单一
- 通过 `tools` 限制权限，提高安全性
- 细化 `description`，让 Claude 知道何时自动委托

## Skill 的 `context: fork` 选项

在 SKILL.md 的 frontmatter 中可以配置 `context: fork`，让技能在**隔离的子代理环境**中运行，而不是在当前对话上下文中执行。

```yaml
---
name: deep-research
description: Research a topic thoroughly
context: fork
agent: Explore
---
```

- 子代理**无法访问**对话历史，技能内容本身成为驱动子代理的提示词
- `agent` 字段可指定子代理类型：`Explore`、`Plan`、`general-purpose`，或自定义 agent
- 技能必须包含**明确的任务指示**，纯指导原则类的技能用 `context: fork` 没有意义

### 什么时候需要用

大多数 skill 不需要 `context: fork`。典型场景是：**不希望当前对话上下文影响 skill 的判断**，比如每次从零开始独立评估的代码审查 skill。

但这些场景用 Agent 工具 + `run_in_background: true` 也能达到类似效果。`context: fork` 更像是一个轻量级替代方案——不用发起 Agent 调用，直接在 skill 里声明隔离运行。

## Skill 批量执行设计模式

当一个 skill 需要支持批量（多文件）执行时，采用三层架构：

```
batch-xxx（skill）──调度层
  └─ xxx-worker（agent）──配置层
       └─ xxx（skill）──执行层
```

### 各层职责

| 层级 | 类型 | 职责 |
| --- | --- | --- |
| **调度层** `batch-xxx` | Skill | 文件列表展开（Glob）、并行分发 Agent、汇总报告 |
| **配置层** `xxx-worker` | Agent | 声明 `permissionMode`、`skills` 依赖和工具白名单，作为调度层与执行层的桥梁 |
| **执行层** `xxx` | Skill | 单文件的实际处理逻辑 |

调度层和执行层分离的好处：单文件 skill 可独立使用，批量 skill 只负责编排，不重复业务逻辑。

### 为什么需要配置层

后台 Agent 需要通过 agent 定义文件提供以下配置，才能可靠地并行调用 skill：

- **`permissionMode: bypassPermissions`**：后台 agent 无法与用户交互，必须跳过权限确认
- **`skills`**：明确声明可用的 skill 依赖，确保后台 agent 能加载和调用目标 skill
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

```
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
  # ... 根据执行层 skill 需要的工具添加
skills:
  - xxx
  # ... 如果执行层 skill 会调用其他 skill，也需要在此声明
permissionMode: bypassPermissions
---

当被调用时，使用 Skill 工具调用 xxx 技能处理指定的文件。
```

关键字段说明：

- **`skills`**：必须声明执行层 skill 及其所有下游 skill 的依赖
- **`permissionMode: bypassPermissions`**：后台 agent 无法与用户交互，需跳过权限确认
- **`tools`**：需包含执行层 skill 所需的所有工具

### 并发安全

#### 检查清单

执行层 skill 必须确保并发安全：

- 不使用固定名称的临时文件（用 `mktemp` 或 PID 后缀）
- 不依赖共享的全局状态
- 每个文件的产出路径互不冲突（如用文件名前缀区分）

#### 标注义务

凡是会被 batch 调度层通过多个并行后台 agent 同时调用的组件，都必须在文件中添加并发安全说明，提醒后续修改者不要引入共享状态。

**需要标注的层级**：

| 层级 | 文件位置 | 说明 |
| --- | --- | --- |
| 配置层 agent | `agents/xxx-worker.md` | 被并发实例化，需确保无共享状态 |
| 执行层 skill | `skills/xxx/SKILL.md` | 实际执行逻辑，最易引入共享状态冲突 |
| 执行层 skill 调用的下游 skill | 如 `md-img-local` | 被间接并发调用，同样需要标注 |

**标注格式**：

在 frontmatter 之后、正文开头处添加 blockquote：

```markdown
> **⚠ 并发安全**：本技能/代理被 `batch-xxx` 通过多个并行后台 agent 同时调用，每个 agent 处理不同文件。修改时，必须确保不引入共享状态（如全局临时文件、固定名称的中间产物等），否则并发执行会产生冲突。
```

**不需要标注的**：调度层 `batch-xxx` 本身（它是调度方，不会被并发调用）。

### 实际案例

`batch-md-fmt`（调度层）→ `md-fmt-worker`（配置层）→ `md-fmt`（执行层）→ `md-img-local`（下游 skill）

## 工作目录

Claude Code 的主工作目录在启动时由当前目录决定，会话中无法更改。如需切换主项目，应在目标目录重新启动 Claude Code。

### 添加额外工作目录

可以在不改变主工作目录的情况下，扩展文件访问范围：

**启动时添加：**

```bash
claude --add-dir /path/to/other/project
```

**会话中添加：**

```
/add-dir /path/to/other/project
```

**持久化配置（settings.json）：**

```json
{
    "additionalDirectories": ["/path/to/other/project"]
}
```

> 注意：额外目录中的 `.claude/` 配置不会被自动发现。

## 防止个人敏感信息泄露

分享 skill 或提交代码时，容易不小心把个人路径（如 `C:\Users\xxx`）、用户名等信息带进去。可以设置两层防护：

### 第一层：Claude Code Hook（写入时检查）

在 `~/.claude/hooks/` 下创建检查脚本和敏感模式文件：

**`~/.claude/hooks/sensitive-patterns`**（每行一个正则）：

```
C:\\Users\\YourName
/home/yourname
YourName
```

**`~/.claude/hooks/check-sensitive-info.sh`**：

```bash
#!/bin/bash
PATTERNS_FILE="$HOME/.claude/hooks/sensitive-patterns"
[ ! -f "$PATTERNS_FILE" ] && exit 0

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ] && exit 0

FOUND=0
while IFS= read -r pattern || [ -n "$pattern" ]; do
    [[ -z "$pattern" || "$pattern" == \#* ]] && continue
    matches=$(grep -inE "$pattern" "$FILE_PATH" 2>/dev/null || true)
    if [ -n "$matches" ]; then
        [ "$FOUND" -eq 0 ] && echo "WARNING: 文件 $FILE_PATH 中检测到敏感个人信息：" && FOUND=1
        echo "  模式 [$pattern]:"
        echo "$matches" | head -5 | sed 's/^/    /'
    fi
done < "$PATTERNS_FILE"

[ "$FOUND" -ne 0 ] && echo "" && echo "请检查并移除上述敏感信息。" && exit 2
```

在 `~/.claude/settings.json` 中注册：

```json
{
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "bash ~/.claude/hooks/check-sensitive-info.sh"
                    }
                ]
            }
        ]
    }
}
```

### 第二层：Git Pre-commit Hook（提交时拦截）

在仓库中创建 `.githooks/pre-commit`，从外部模式文件读取正则，扫描暂存区内容，匹配到敏感信息则阻止提交。

关键设计：模式文件（`.githooks/sensitive-patterns`）加入 `.gitignore` 不提交，仓库中只保留 `.githooks/sensitive-patterns.example` 作为模板。

```bash
# 启用 hook
git config core.hooksPath .githooks
cp .githooks/sensitive-patterns.example .githooks/sensitive-patterns
# 编辑填入个人信息模式
```

两层配合：Claude 写文件时**立刻警告**，git commit 时**兜底拦截**。

## Agent Team（多智能体协作）

Agent Team 是 Claude Code 的实验性功能，支持多个智能体并行协作，默认禁用。

### 启用方法

在 `~/.claude/settings.json` 的 `env` 字段中添加：

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

或设置系统环境变量：

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

### 使用方式

启用后用自然语言描述团队即可创建，例如：

> 创建一个 agent team，一个负责前端开发，一个负责后端 API，一个负责写测试。

### 核心特点

- 每个 teammate 有独立 context window，可互相通讯
- 共享任务列表，所有成员可以看到任务状态、认领工作
- 适合研究审查、多模块并行开发、bug 调查、跨层协调等场景

### 注意事项

- 需要 Claude Code v2.1.32+
- 一个会话只能管理一个团队
- 实验性功能，不支持 `/resume` 会话恢复

## 订阅套餐与使用限制

> **注意**：Anthropic 官方不公布精确 token 阈值，只承诺相对倍数。以下数字来源于第三方社区测试（2026 年 4 月），仅供参考，会随 Anthropic 调整而变化。

### 套餐概览

| 套餐 | 月费 | 每 5 小时窗口（估算提示数） | 估算 token 阈值 |
| --- | --- | --- | --- |
| Free | $0 | 2-5 条 | ~5K |
| Pro | $20 | 10-40 条 | ~44K |
| Max 5x | $100 | 50-200 条 | ~88K |
| Max 20x | $200 | 200-800 条 | ~220K |

提示数变化大——一条复杂长对话消耗的 token 可能是简单问题的 10 倍以上。

### 每周限制（2025 年 8 月起）

| 套餐 | 每周 Sonnet 时间 | 每周 Opus 时间 |
| --- | --- | --- |
| Pro | 40-80h | 不可用 |
| Max 5x | 140-280h | 15-35h |
| Max 20x | 240-480h | 24-40h |

### 模型成本差异

| 模型 | 输入 ($/M tokens) | 输出 ($/M tokens) | 备注 |
| --- | --- | --- | --- |
| Opus 4.6 | $5 | $25 | 最强但最贵，消耗配额约为 Sonnet 的 1.7 倍 |
| Sonnet 4.6 | $3 | $15 | 性价比均衡 |
| Haiku 4.5 | $1 | $5 | 最便宜，简单任务首选 |

- **长上下文溢价**（>200K tokens）：Opus $10/$37.50，Sonnet $6/$22.50
- **Fast 模式**：Opus 4.6 为标准费率的 6 倍
- **Batch API**：5 折

### 超额使用（Extra Usage）

Pro/Max 用户达到限额后可按 API 标准费率继续使用，每日充值上限 $2,000，可设月度消费上限。

### 来源

- [Claude Help Center - Manage Extra Usage](https://support.claude.com/en/articles/12429409-manage-extra-usage-for-paid-claude-plans)
- [Claude Code Limits - Portkey](https://portkey.ai/blog/claude-code-limits/)
- [Claude Code Token Limits - Faros](https://www.faros.ai/blog/claude-code-token-limits)

## 省 Token 最佳实践

### 第一梯队：效果最显著

#### 选对模型

```
/model    # 切换模型
```

- **Opus**：仅用于复杂多文件重构、架构决策
- **Sonnet**：日常开发、写测试、中等复杂度
- **Haiku**：快速查询、格式化、简单问答

Max 5x 为例：Opus 周限额 15-35h，Sonnet 140-280h，差距巨大。

#### 一个任务一个会话

每次发消息 Claude 都会重读整个对话历史。第 1 条约 500 tokens，第 30 条可能 15,000 tokens。

- 完成任务后 `/clear`
- 不在同一会话混合不相关任务

#### 主动 `/compact`

上下文使用约 50% 时执行，压缩对话摘要释放空间：

```
/compact Focus on the API changes    # 可指定压缩重点
```

#### 精确的提示词

| 差 | 好 |
| --- | --- |
| "修一下登录 bug" | "用户反馈 session 过期后登录失败，检查 src/auth/ 的 token 刷新" |
| "给 foo.py 加测试" | "给 foo.py 的用户登出场景写测试，不要用 mock" |
| "这个文件怎么回事" | "解释 src/services/user.ts 第 47 行的认证错误" |

模糊提示迫使 Claude 先搜索、分析、猜测，浪费大量 token。

### 第二梯队：日常好习惯

#### `.claudeignore` 排除无关文件

```
node_modules/
build/
dist/
*.log
package-lock.json
```

#### 精简 CLAUDE.md

每次会话启动都会读取，5,000 tokens 的 CLAUDE.md = 每次交互先被"征税" 5,000 tokens。保持在 2,000 tokens 以内，只放 Claude 无法从代码推断的信息。

#### 用子代理做调研

子代理在独立上下文窗口运行，返回摘要，不污染主会话。

```
用子代理调查我们的认证系统如何处理 token 刷新
```

#### 用 `@` 引用文件

```
看一下 @src/auth/login.ts    # 好：直接引用
看一下登录相关的代码          # 差：Claude 要先搜索
```

### 第三梯队：进阶技巧

- **`/rewind` 代替反复纠正**：走错方向时回退检查点，避免在上下文里堆积无效尝试
- **错峰使用**：美东时间工作日 8AM-2PM 限额更紧，大任务安排在下午/晚上/周末
- **监控用量**：`/usage` 查看会话和周用量；`claude-hud` 插件实时监控上下文
- **非交互模式**：`claude -p "运行测试"` 比交互式省 token
- **`/btw` 侧问**：快速提问不进入对话历史，不增长上下文

### 常见反模式

| 反模式 | 症状 | 解决 |
| --- | --- | --- |
| 厨房水槽会话 | 一个会话做多个不相关任务 | `/clear` 隔离任务 |
| 反复纠正 | 连续纠正 2 次以上 | `/clear` 后用更好的初始提示重来 |
| CLAUDE.md 过长 | 规则被忽略 | 精简到 2,000 tokens 以内 |
| 无限探索 | 要求"调查"但不限范围 | 限定范围，或用子代理 |
| 信任但不验证 | 看起来对但缺少测试 | 提供测试/脚本/截图作为验证 |

### 来源

- [Best Practices - Claude Code Official Docs](https://code.claude.com/docs/en/best-practices)
- [12 Proven Techniques to Save Tokens - Aslam Doctor](https://aslamdoctor.com/12-proven-techniques-to-save-tokens-in-claude-code/)
- [Claude Code Token Limits - Faros](https://www.faros.ai/blog/claude-code-token-limits)
