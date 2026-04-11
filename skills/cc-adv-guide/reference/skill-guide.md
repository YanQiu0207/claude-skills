# Claude Code Skills 完整字段参考

> 来源：[官方文档](https://code.claude.com/docs/en/skills)、[Anthropic 官方 PDF 指南](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf)、[Agent Skills 开放标准规范](https://agentskills.io/specification)

## 一、YAML Frontmatter 全部字段

Skills 文件是 `SKILL.md`，顶部用 `---` 包裹 YAML frontmatter。**所有字段均为可选**。

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | 字符串 | 目录名 | 技能的显示名称，也是 `/slash-command` 的名称。仅允许小写字母、数字、连字符，最长 64 字符，不能以连字符开头/结尾，不允许连续连字符，不能包含 "claude" 或 "anthropic" |
| `description` | 字符串 | SKILL.md 第一段 | **强烈推荐**。描述技能做什么、何时使用。Claude 用它决定是否自动加载该技能。超过 250 字符会在列表中截断，最长 1024 字符 |
| `argument-hint` | 字符串 | - | 自动补全时显示的参数提示，如 `[issue-number]` 或 `[filename] [format]` |
| `disable-model-invocation` | 布尔值 | `false` | 设为 `true` 阻止 Claude 自动调用此技能，只能由用户通过 `/name` 手动触发 |
| `user-invocable` | 布尔值 | `true` | 设为 `false` 从 `/` 菜单隐藏，仅供 Claude 自动调用（背景知识类） |
| `allowed-tools` | 字符串或列表 | - | 技能激活时 Claude 可无需确认使用的工具。空格分隔字符串或 YAML 列表 |
| `model` | 字符串 | 继承会话 | 技能激活时使用的模型覆盖 |
| `effort` | 字符串 | 继承会话 | 技能激活时的 effort 级别。可选 `low`、`medium`、`high`、`max`（仅 Opus 4.6） |
| `context` | 字符串 | - | 设为 `fork` 在独立的子代理上下文中运行 |
| `agent` | 字符串 | `general-purpose` | 当 `context: fork` 时使用的子代理类型。可选 `Explore`、`Plan`、`general-purpose` 或 `.claude/agents/` 中的自定义代理 |
| `hooks` | 对象 | - | 限定于此技能生命周期的 hooks |
| `paths` | 字符串或列表 | - | Glob 模式，限制技能仅在处理匹配文件时激活。适用于 monorepo 的路径特定技能 |
| `shell` | 字符串 | `bash` | 技能中内联 shell 命令使用的 shell。可选 `bash` 或 `powershell` |

---

## 二、字符串替换变量

SKILL.md 的 Markdown 正文中可使用以下动态变量：

| 变量 | 说明 |
|---|---|
| `$ARGUMENTS` | 用户调用技能时传入的全部参数。若正文中没有此变量，参数会自动追加为 `ARGUMENTS: <value>` |
| `$ARGUMENTS[N]` | 按 0 基索引访问特定参数，如 `$ARGUMENTS[0]` |
| `$N` | `$ARGUMENTS[N]` 的简写，如 `$0`、`$1` |
| `${CLAUDE_SESSION_ID}` | 当前会话 ID |
| `${CLAUDE_SKILL_DIR}` | 包含 `SKILL.md` 的目录路径（独立于工作目录） |

---

## 三、调用控制矩阵

| 配置 | 用户可调用 | Claude 可自动调用 | 典型用途 |
|---|---|---|---|
| 默认（两个都不设） | 是 | 是 | 通用技能 |
| `disable-model-invocation: true` | 是 | 否 | 有副作用的操作（deploy、commit） |
| `user-invocable: false` | 否 | 是 | 背景知识、约定规范 |

---

## 四、动态上下文注入

在 SKILL.md 正文中用 `!command` 语法，技能发送给 Claude **之前**先执行 shell 命令，输出直接替换占位符：

```markdown
## 当前上下文
- 分支: !`git branch --show-current`
- PR diff: !`gh pr diff`
- 变更文件: !`gh pr diff --name-only`
```

多行命令使用 ` ```! ` 代码块：

````markdown
```!
node --version
npm --version
git status --short
```
````

在技能内容中任意位置包含 "ultrathink" 一词可触发 extended thinking。

---

## 五、最佳实践

### 1. description 的写法

结构：**[做什么] + [何时使用] + [能力]**

```yaml
# 好
description: >
  Extracts text and tables from PDF files, fills PDF forms,
  and merges multiple PDFs. Use when working with PDF documents
  or when the user mentions PDFs, forms, or document extraction.

# 差
description: "Helps with PDFs."
```

description 是驱动 Claude 自动激活的核心——前置关键用例，因为 250 字符后会被截断。

### 2. 文件组织（渐进式披露）

三层架构，控制 token 消耗：

| 层级 | 内容 | 何时加载 | Token 预算 |
|---|---|---|---|
| 元数据 | `name` + `description` | 启动时**所有**技能加载 | ~100 token/技能 |
| 指令 | SKILL.md 正文 | 技能被调用时加载 | 建议 < 5000 token |
| 资源 | `scripts/`、`references/`、`assets/` | 正文中引用时按需加载 | 无限制 |

保持 SKILL.md **500 行以内**，详细参考移到独立文件：

```
my-skill/
├── SKILL.md              # 必需 - 核心指令
├── reference.md          # 详细 API/规范文档
├── examples.md           # 用例示例
└── scripts/
    └── helper.py         # 辅助脚本
```

### 3. 注意事项

- 技能文件夹内**不要放 README.md**
- YAML 中**不能有** XML 尖括号（`<` `>`）
- 技能调用后作为单条消息进入对话，整个会话保持不变（不会重新读取）
- Auto-compaction 保留每个技能最近一次调用的前 5,000 token，所有技能共享 25,000 token 预算
- name 字段中不能包含 "claude" 或 "anthropic"

---

## 六、官方示例

### 示例 1：参考知识类（默认，Claude 可自动调用）

```yaml
---
name: api-conventions
description: >
  API design patterns and conventions for this codebase.
  Use when writing or reviewing API endpoints.
---

When writing API endpoints:
1. Use RESTful naming conventions
2. Return consistent error formats
3. Include request validation middleware
```

### 示例 2：手动触发工作流（disable-model-invocation）

```yaml
---
name: deploy
description: Deploy the application to production
disable-model-invocation: true
---

Deploy $ARGUMENTS to production:
1. Run the test suite
2. Build the application
3. Push to the deployment target
4. Verify the deployment succeeded
```

### 示例 3：工具预授权

```yaml
---
name: commit
description: Stage and commit the current changes
disable-model-invocation: true
allowed-tools: Bash(git add *) Bash(git commit *) Bash(git status *)
---

Stage and commit changes with a descriptive message.
Follow conventional commit format.
```

### 示例 4：子代理 fork + 动态上下文

```yaml
---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
allowed-tools: Bash(gh *)
---

## Pull request context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`

Summarize this pull request concisely.
```

### 示例 5：位置参数

```yaml
---
name: migrate-component
description: Migrate a component from one framework to another
---

Migrate the $0 component from $1 to $2.
Preserve all existing behavior and tests.
```

调用方式：`/migrate-component Button React Vue`

### 示例 6：脚本捆绑型

```yaml
---
name: codebase-visualizer
description: >
  Generate an interactive collapsible tree visualization of your codebase.
allowed-tools: Bash(python *)
---

Run the visualization script from your project root:

python ${CLAUDE_SKILL_DIR}/scripts/visualize.py .
```

---

## 七、技能存放位置与优先级

| 级别 | 路径 | 范围 |
|---|---|---|
| Enterprise | 通过 managed settings 管理 | 组织内所有用户 |
| Personal | `~/.claude/skills/<name>/SKILL.md` | 你的所有项目 |
| Project | `.claude/skills/<name>/SKILL.md` | 仅当前项目 |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | 启用插件的地方 |

优先级：**Enterprise > Personal > Project**。同名时 skill 优先于旧版 command。

---

## 八、五种常见技能模式

来源：Anthropic 官方 PDF 指南

1. **Sequential Workflow Orchestration** -- 多步骤流程，有特定顺序要求
2. **Multi-MCP Coordination** -- 跨多个服务（Figma -> Drive -> Linear -> Slack）
3. **Iterative Refinement** -- 通过迭代改进输出（报告生成等）
4. **Context-Aware Tool Selection** -- 根据上下文选择不同工具实现相同结果
5. **Domain-Specific Intelligence** -- 嵌入专业领域知识（合规检查、财务规则等）

---

## 参考来源

- [官方文档 -- Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [Anthropic 官方 PDF 指南](https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf)
- [Agent Skills 开放标准规范](https://agentskills.io/specification)
- [Anthropic 官方技能仓库](https://github.com/anthropics/skills)
