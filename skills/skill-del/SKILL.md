---
name: skill-del
description: 安全删除 skill，自动扫描并处理所有依赖关系（其他 skill、agent 中的引用），确保删除后系统一致。当需要删除一个 skill 时使用此技能。
argument-hint: "[技能名称]"
disable-model-invocation: true
model: sonnet
---

# Skill Delete

安全删除 skill，自动扫描并处理所有依赖关系。

## When to Use

- 需要删除一个不再使用的 skill
- skill 的功能已被其他方式替代（如迁移到参考文件、合并到另一个 skill 等）

## Inputs

```
- skill_name: 要删除的 skill 名称（例如 "md-zh"）
```

## Procedure

### Step 1: 定位并确认目标 skill

1. 在 `~/.claude/skills/` 中查找对应目录
2. 读取 `SKILL.md`，显示 `name` 和 `description`
3. 如果目录不存在，报错并停止

### Step 2: 全局搜索引用

在以下位置搜索对目标 skill 的所有引用：

**搜索范围**（仅扫描定义文件，忽略历史/缓存）：
- `~/.claude/skills/*/SKILL.md` — 其他 skill 定义
- `~/.claude/agents/*.md` — agent 定义

**搜索模式**：
1. **frontmatter 依赖**：`skills:` 列表中包含目标名称
2. **Skill 工具调用**：`调用 \`skill_name\` 技能`、`使用 Skill 工具调用 \`skill_name\``
3. **反引号引用**：`` `skill_name` ``
4. **纯文本提及**：`skill_name`（不在反引号内）

将结果按文件分组，标注每处引用的行号和上下文。

### Step 3: 向用户展示影响分析

输出影响分析报告，格式：

```
## 影响分析：删除 skill_name

### 目标 skill
- 路径：~/.claude/skills/skill_name/SKILL.md
- 描述：...

### 发现 N 处引用

#### 1. skills/other-skill/SKILL.md
- 第 22 行：`调用 \`skill_name\` 技能加载排版规则`
- 第 26 行：`按照 skill_name 的规则逐项检查`

#### 2. agents/some-agent.md
- 第 11 行（frontmatter skills 列表）：`- skill_name`
- 第 24 行：`排版规范已通过 skill_name skill 加载`
```

如果**没有发现任何引用**，告知用户可以安全删除，跳到 Step 5。

如果**存在引用**，询问用户如何处理每个引用文件：
- **替换**：将引用改为用户指定的替代方案（如参考文件路径、另一个 skill 等）
- **移除**：直接删除引用行（适用于 frontmatter 列表项、工具声明等）
- **跳过**：保留该引用不处理（用户自行修复）

### Step 4: 备份

在进行任何修改前，创建备份：

1. **备份目录**：`~/.claude/skills/skill_name.bak/`，完整复制目标 skill 目录
2. **备份引用文件**：对每个即将修改的文件，在同目录下创建 `.bak` 副本（如 `SKILL.md.bak`）
3. 输出备份清单，告知用户备份位置

### Step 5: 处理引用

根据用户的指示，逐文件处理引用：

**frontmatter `skills:` 列表**：
- 从列表中移除目标 skill 名称
- 如果列表变空，移除整个 `skills:` 字段

**frontmatter `tools:` 列表**：
- 如果 `Skill` 工具仅用于调用目标 skill，一并移除 `- Skill`
- 如果还有其他 skill 在用，保留 `- Skill`

**正文中的引用**：
- 按用户指定的替代方案修改
- 替换时注意保持上下文通顺

每处修改完成后，简要说明改了什么。

### Step 6: 删除 skill 目录

确认所有引用已处理后，删除目标 skill 的整个目录：

```bash
rm -rf ~/.claude/skills/skill_name
```

### Step 7: 验证

1. 确认目录已删除
2. 再次在 `~/.claude/skills/` 和 `~/.claude/agents/` 中搜索目标名称
3. 如有残留引用（Step 3 中用户选择跳过的除外），发出警告

### Step 8: 生成删除报告

```
## Skill 删除报告

### 基本信息
- 名称：skill_name
- 状态：已删除

### 引用处理
| 文件 | 引用数 | 处理方式 |
|------|--------|----------|
| skills/other/SKILL.md | 3 | 替换为 `~/.claude/claude_ref/xxx.md` |
| agents/some.md | 2 | 移除 |

### 验证结果
- 目录已删除：✓
- 残留引用：0 处

### 回滚信息
如需撤销，执行以下命令：
\`\`\`bash
# 恢复 skill 目录
cp -r ~/.claude/skills/skill_name.bak ~/.claude/skills/skill_name
# 恢复引用文件
cp path/to/SKILL.md.bak path/to/SKILL.md
...
\`\`\`
备份文件将保留 24 小时供回滚使用，确认无误后可手动删除。
```

## Edge Cases

### 1. skill 不存在
→ 报错：找不到对应的 skill 目录，退出

### 2. 无任何引用
→ 直接备份并删除，报告中注明无需处理引用

### 3. 循环依赖
→ 如果目标 skill 被 A 依赖，A 又被 B 依赖，只处理直接引用；间接影响在报告中提示用户注意

### 4. 用户中途取消
→ 使用备份文件恢复所有已修改的文件，恢复已删除的 skill 目录，最后清理 `.bak` 文件
→ 告知用户已完全回滚到操作前状态
