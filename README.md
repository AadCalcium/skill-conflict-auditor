# skill-conflict-auditor 使用文档

`skill-conflict-auditor` 是一个用于检查 Codex skills 冲突的半自动审计 skill。它可以扫描已安装的 skills，也可以把你新写的某个 skill 与现有 skills 做对比，找出命名、触发范围、工作流、工具偏好、输出格式和资源引用等方面的潜在冲突。

它的默认策略是安全优先：只生成报告和建议补丁，不直接修改任何 skill。

## 适用场景

- 安装多个 skills 后，想检查它们是否互相抢触发。
- 写了一个新 `SKILL.md`，想在安装前检查是否和已有 skills 冲突。
- 想找出重复的 skill 名称、相似描述、过宽泛的触发规则。
- 想检查 skill 是否缺少 `name`、`description` 或 frontmatter 格式错误。
- 想生成可审查的 patch，但不希望脚本直接修改文件。
- 想在 CI 或自动化流程里发现高风险 skill 冲突。

## 文件结构

当前 skill 位于：

```text
/Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor
```

主要文件：

```text
skill-conflict-auditor/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── audit_skill_conflicts.py
```

其中：

- `SKILL.md`：告诉 Codex 什么时候使用这个 skill，以及基本工作流。
- `agents/openai.yaml`：Codex UI 展示信息。
- `scripts/audit_skill_conflicts.py`：实际执行扫描、冲突判断、报告生成和 patch 生成的脚本。

## 检测内容

脚本会检查以下类型的问题：

- skill 名称重复。
- skill 名称高度相似。
- 缺少 `SKILL.md` frontmatter。
- frontmatter 中缺少 `name` 或 `description`。
- 文件夹名称与 skill 名称明显不一致。
- `description` 触发范围过宽，可能抢占其他 skills。
- 多个 skills 的触发描述高度重叠。
- 工作流策略冲突，例如一个要求先问用户，另一个要求直接执行。
- 工具偏好冲突，例如 browser、chrome、figma、github 等工具使用范围重叠。
- 输出格式冲突，例如一个偏 Markdown，一个偏 HTML 或 JSON。
- 引用的本地资源缺失，例如 `scripts/`、`references/`、`assets/` 下的文件。
- 相似 skills 中出现同名脚本，可能代表重复实现或维护风险。

## 基本用法

进入 skill 目录：

```bash
cd /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor
```

执行一次默认审计：

```bash
python3 scripts/audit_skill_conflicts.py \
  --output-dir ../skill-conflict-auditor-report
```

默认会扫描：

- `$CODEX_HOME/skills`
- `$CODEX_HOME/plugins/cache`
- 如果没有设置 `$CODEX_HOME`，则使用 `~/.codex`
- 当前工作区内能发现的 skills

## 检查一个新 skill

如果你写了一个新 skill，想检查它是否和已有 skills 冲突：

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

`--new-skill` 可以传 skill 文件夹，也可以直接传 `SKILL.md`：

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill/SKILL.md \
  --output-dir ./skill-conflict-auditor-report
```

默认情况下，如果生成 `suggested_fixes.patch`，它只会包含新 skill 的修改建议。已安装 skills 会出现在报告里，但不会默认进入 patch。

## 指定扫描目录

你可以显式指定扫描范围：

```bash
python3 scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --root ~/.codex/plugins/cache \
  --root /path/to/project/skills \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

`--root` 可以重复使用。适合你有多个自定义 skills 目录，或者想只审计某几个目录时使用。

## 输出文件

每次运行会生成 3 个文件：

```text
conflict_report.md
conflict_report.json
suggested_fixes.patch
```

### conflict_report.md

人类阅读优先的报告。建议先看这个文件。

它包含：

- 扫描了多少 skills。
- 发现了多少 high、medium、low 问题。
- 每个 finding 的类型、详情、涉及文件和建议。
- 所有被扫描 skills 的摘要。

### conflict_report.json

机器可读报告。适合后续脚本处理、做仪表盘、做 CI 集成。

它包含：

- `summary`
- `findings`
- `skills`

### suggested_fixes.patch

统一 diff 格式的建议补丁。

默认只生成，不应用。你需要人工审查后再决定是否应用。

## Patch 范围

通过 `--patch-scope` 控制哪些文件允许进入 patch：

```bash
--patch-scope candidate
```

默认值。只给 `--new-skill` 指定的候选 skill 生成 patch。

```bash
--patch-scope personal
```

允许给候选 skill 和 `~/.codex/skills` 下的个人 skills 生成 patch。

```bash
--patch-scope all
```

允许给所有扫描到的 skills 生成 patch，包括插件缓存里的 skills。这个模式风险较高，建议只用于实验或复制出来的测试目录。

## CI 模式

默认情况下，即使发现 high 级别问题，脚本也会退出成功。这是为了适合日常审计，不让报告生成流程被中断。

如果你希望在 CI 中发现 high 问题时失败，可以加：

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --fail-on-high
```

开启后，只要存在 high severity findings，脚本会返回非 0 退出码。

## 严重等级说明

### High

通常代表需要优先处理的问题。

常见 high 问题：

- skill 名称重复。
- frontmatter 缺失。
- `name` 或 `description` 缺失。

### Medium

通常代表可能影响触发准确性或维护质量的问题。

常见 medium 问题：

- description 太宽泛。
- 触发描述明显重叠。
- 工作流策略冲突。
- 引用资源缺失。

### Low

通常代表需要人工确认的维护风险。

常见 low 问题：

- 工具使用范围重叠。
- 输出格式部分冲突。
- 脚本名称重复。
- 文件夹名称和 skill 名称不完全一致。

## 推荐工作流

### 安装前检查新 skill

1. 写好新 skill。
2. 运行：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --output-dir /path/to/report
```

3. 先读 `conflict_report.md`。
4. 再看 `suggested_fixes.patch`。
5. 确认无误后再手动应用 patch。

### 定期检查所有 skills

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --output-dir /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor-report
```

适合在安装新插件、复制 skills、升级 Codex 环境后运行。

### 审计个人 skills 并生成修复建议

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --patch-scope personal \
  --output-dir ./skill-conflict-auditor-report
```

这个模式会给个人 skills 生成建议 patch，但仍然不会自动应用。

## 当前验证结果

在当前环境中，脚本已经成功运行过一次：

```text
Scanned 59 skills.
Findings: 55 total, 5 high, 27 medium, 23 low.
```

生成的报告位于：

```text
/Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor-report
```

当前发现的 high 问题主要是已有环境中存在重复 skill 名称，例如：

- `figma-create-new-file`
- `figma-generate-design`
- `figma-generate-library`
- `figma-use`
- `github`

这些问题来自已安装 skills 或插件缓存之间的重复，不是 `skill-conflict-auditor` 本身的错误。

## 注意事项

- 这个工具是启发式检测，不是绝对判定。
- Medium 和 low findings 应该由人工复核。
- 不建议直接修改插件缓存目录里的 skills，除非你明确知道后果。
- `suggested_fixes.patch` 永远应该先审查，再应用。
- 如果某个 skill 的 description 故意写得很宽泛，可以忽略对应 finding，或在 skill 中增加更清楚的边界说明。

## 常用命令速查

全量审计：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --output-dir /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor-report
```

检查新 skill：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

只扫描个人 skills：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --output-dir ./skill-conflict-auditor-report
```

生成个人 skills 的 patch：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --patch-scope personal \
  --output-dir ./skill-conflict-auditor-report
```

CI 中发现 high 问题则失败：

```bash
python3 /Users/zhangye/Documents/Codex/SKill/skill-conflict-auditor/scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --fail-on-high
```
