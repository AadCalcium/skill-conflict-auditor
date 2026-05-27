# skill-conflict-auditor 使用文档

`skill-conflict-auditor` 用来检查 Codex skills 之间是否存在冲突，并生成报告和建议补丁。它默认是半自动模式：只输出结果，不直接修改你的 skills。

## 能检查什么

- skill 名称重复或相似。
- `description` 触发范围重叠或过宽。
- `SKILL.md` frontmatter 缺失或格式错误。
- 工作流冲突，例如一个要求先问用户，另一个要求直接执行。
- 工具或输出格式冲突，例如 browser/chrome、Markdown/HTML/JSON。
- 引用的 `scripts/`、`references/`、`assets/` 文件缺失。

## 文件结构

```text
skill-conflict-auditor/
├── SKILL.md
├── agents/openai.yaml
└── scripts/audit_skill_conflicts.py
```

## 常用命令

全量扫描已安装 skills：

```bash
python3 scripts/audit_skill_conflicts.py \
  --output-dir ./skill-conflict-auditor-report
```

检查一个新 skill：

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

指定扫描目录：

```bash
python3 scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --root ~/.codex/plugins/cache \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

CI 中遇到 high 问题时失败：

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --fail-on-high
```

## 输出结果

运行后会生成：

- `conflict_report.md`：给人看的冲突报告。
- `conflict_report.json`：给脚本或自动化读取的报告。
- `suggested_fixes.patch`：建议修改补丁，默认不会自动应用。

## Patch 范围

默认只给 `--new-skill` 指定的新 skill 生成补丁。

可选范围：

```bash
--patch-scope candidate
--patch-scope personal
--patch-scope all
```

建议日常使用默认的 `candidate`。`all` 会包含插件缓存里的 skills，谨慎使用。

## 注意

这个工具是启发式检测，不是绝对判定。`high` 优先处理，`medium` 和 `low` 建议人工复核。任何 patch 都应该先看一遍，再决定是否应用。
