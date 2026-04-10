---
name: skill-rename
description: 为 skill 改名，同时自动检查和更新所有依赖关系。当需要重命名一个 skill 时使用此技能。功能包括：1) 扫描 skill 结构找出名称和依赖；2) 扫描所有其他 skill 文件，找出对该 skill 的引用；3) 批量更新引用；4) 验证 YAML frontmatter 有效性；5) 生成完整的变更报告。
argument-hint: "[旧名称] [新名称]"
disable-model-invocation: true
model: sonnet
---

# Skill Rename

为 skill 改名，同时自动检查和更新所有依赖关系。

## Summary

此 skill 帮助你在重命名 skill 时保持完整性。它会：

1. **扫描目标 skill** — 识别当前名称和结构
2. **全局搜索引用** — 在所有 skill 文件中找出对该 skill 的引用（反引号、文本提及等）
3. **批量更新引用** — 自动更新所有找到的引用
4. **重命名目录** — 重命名 skill 目录（可选）
5. **验证有效性** — 检查更新后的 YAML frontmatter 是否有效
6. **生成报告** — 输出详细的变更清单

## When to Use

- 需要给一个 skill 改名
- skill 已经被其他 skill 依赖，需要更新依赖关系
- 需要确保改名后的一致性和完整性

## When Not to Use

- 仅需要修改 skill 的 description（用编辑工具即可）
- 需要删除整个 skill（这是销毁操作，不是改名）

## Success Criteria

改名完成时：
1. ✓ SKILL.md 的 `name:` 字段已更新
2. ✓ 所有其他 skill 文件中的引用已更新
3. ✓ 目录已重命名（如适用）
4. ✓ YAML frontmatter 验证通过
5. ✓ 变更报告中列出了所有修改的文件和具体改动

## Inputs

```
- old_name: 当前的 skill 名称（例如 "markdown-localize"）
- new_name: 新的 skill 名称（例如 "md-image-localize"）
- rename_directory: 是否同时重命名目录 [Y/n，默认 Y]
```

## Outputs

变更报告包含：
- 修改的文件列表
- 每个文件中的具体改动
- YAML 验证结果
- 如有失败，失败原因和恢复步骤

## Procedure

### Step 1: 定位 skill 和验证名称

1. 在 `~/.claude/skills/` 中查找目录
2. 打开对应的 `SKILL.md`，读取 frontmatter 中的 `name:` 字段
3. 验证提供的 `old_name` 与实际名称匹配
4. 如果不匹配，报错并停止

### Step 2: 全局搜索引用

扫描 `~/.claude/skills/` 中的所有 SKILL.md 文件，寻找以下形式的引用：

1. **反引号形式**：`` `old_name` ``
2. **使用 Skill 工具调用**：
   - `使用 Skill 工具调用 \`old_name\` 技能`
   - `调用 \`old_name\` 技能`
3. **YAML frontmatter 中的引用**（如存在）：
   - `compatibility: requires: [old_name]`
   - `depends_on: [old_name]`
   - 其他自定义字段
4. **注释形式**：
   - `# depends on old_name`
   - `# 需要调用 old_name`
5. **链接或路径形式**：
   - `[old_name](../old_name/SKILL.md)`
   - 其他对目录名的引用
6. **其他上下文** — 排除 SKILL.md 本身和无关内容

### Step 2.5: 自动备份

在进行任何修改前，为所有将要修改的文件创建备份：
1. 对于每个即将修改的 SKILL.md，创建备份副本（`.backup`）
2. 对于目录重命名，记录完整的目录树
3. 生成备份清单，供后续恢复使用

### Step 3: 更新所有引用

对于每个发现的引用：
1. 替换反引号中的名称：`` `old_name` `` → `` `new_name` ``
2. 如果有其他文本形式的提及，也一并更新
3. 更新 YAML frontmatter 中的引用
4. 更新注释中的引用
5. 保留原有的格式和缩进

### Step 4: 更新目标 skill 的 SKILL.md

修改目标 skill 的 SKILL.md frontmatter：
- 将 `name: old_name` 改为 `name: new_name`
- 保留其他字段（description, argument-hint 等）不变

### Step 5: 重命名目录和更新路径引用（可选）

如果 `rename_directory` 为 Y：

1. **重命名目录**：
   - 获取当前目录路径（例如 `~/.claude/skills/old_name/`）
   - 创建新目录或移动现有目录到新名称（`new_name\`）

2. **更新配置文件中的路径引用**：
   - 扫描所有配置文件（如 `.claude/settings.json`、项目级别的配置等）
   - 寻找对旧目录的路径引用（例如 `path: skills/old_name`)
   - 更新为新路径（`path: skills/new_name`）

3. **更新 SKILL.md 中的路径引用**：
   - 更新脚本、资源、参考文件的相对路径（如有）
   - 确保目录结构一致

### Step 6: 验证 YAML 有效性

对修改后的每个 SKILL.md 执行 YAML 验证：
1. 检查 frontmatter 语法是否有效
2. 确保必需字段（name, description）存在
3. 如果验证失败，输出具体的错误位置

### Step 7: 生成变更报告

输出以下信息：

```
# Skill 改名报告

## 基本信息
- 旧名称：old_name
- 新名称：new_name
- 目录重命名：Y/N
- 状态：成功/失败

## 修改文件列表

### 1. skill-name/SKILL.md
- 修改行：2
- 改动：name: old_name → name: new_name

### 2. other-skill/SKILL.md
- 修改行：15
- 改动：\`old_name\` → \`new_name\`

...

## 验证结果
- YAML 有效性：✓ 通过
- 引用完整性：✓ 已更新 N 处引用
- 目录状态：✓ 已重命名

## 汇总
- 修改文件数：N
- 更新引用数：M
- 失败文件数：0
```

## Edge Cases

### 1. 旧名称与新名称相同
→ 报错：没有实际改动，退出

### 2. 新名称已存在
→ 报错：新名称已被其他 skill 使用，拒绝改名

### 3. 目录不存在
→ 报错：找不到对应的 skill 目录

### 4. 引用形式多样化
→ 使用宽松的正则匹配，捕捉各种合理形式

### 5. 部分文件更新失败
→ 报告失败的文件和原因，但继续处理其他文件
→ 在最终报告中标记失败状态
→ 自动恢复已创建的备份，确保系统返回一致状态

### 6. 恢复失败改名
如果需要撤销改名操作：
→ 找到备份文件（`.backup`）
→ 恢复备份（`mv old_name.backup old_name`）
→ 恢复目录（如有重命名）
→ 报告恢复完成

## Implementation Strategy

1. **使用脚本** — 使用 Python 或 Bash 脚本进行文件操作和正则替换
2. **验证工具** — 使用 YAML 验证库（如 pyyaml）检查前置元数据
3. **安全操作** — 在修改前自动创建备份（`.backup` 文件），失败时可完全恢复
4. **详细日志** — 记录每一步的操作和结果，便于追踪
5. **多种搜索模式** — 支持反引号、YAML 字段、注释、链接等多种引用形式

## Minimal Checklist

执行前：
- [ ] 确认 old_name 和 new_name 都已提供
- [ ] 确认目标 skill 目录存在
- [ ] 理解 rename_directory 参数的含义

执行中：
- [ ] 已扫描所有 SKILL.md 文件
- [ ] 已找出所有引用
- [ ] 已备份原文件（可选但推荐）

执行后：
- [ ] 所有文件已更新
- [ ] YAML 验证通过
- [ ] 生成了完整的变更报告
- [ ] 用户确认了改动

## One-Line Rule

**安全、完整、可追踪地为 skill 改名，确保所有依赖关系同步更新，无遗漏。**
