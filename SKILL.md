---
name: skill-conflict-auditor
description: Audit AI agent skills, capabilities, commands, and instruction packages for conflicts across Claude Code, Codex, OpenClaw, and similar agent environments. Use when checking installed or newly written SKILL.md-style packages, finding overlapping triggers or names, detecting malformed metadata, or generating semi-automatic fix patches without applying them.
---

# Skill Conflict Auditor

Use this skill to inspect AI agent skill/capability packages for conflicts and produce a reviewable fix plan. It is designed to work across Claude Code, Codex, OpenClaw, and similar agent systems.

It supports both:

- Full audit: scan installed skills/capabilities.
- Candidate audit: compare one new or edited skill/capability against installed ones.

Default behavior is semi-automatic: generate reports and a patch file, but do not modify existing files unless the user explicitly asks to apply a specific patch.

## Workflow

1. Identify scan roots.
   - Codex: `$CODEX_HOME/skills`, `$CODEX_HOME/plugins/cache`, `~/.codex`.
   - Claude Code: `~/.claude` or any explicit project instruction/command path.
   - OpenClaw: `$OPENCLAW_HOME`, `~/.openclaw`, or any explicit capability path.
   - Current project: the user's workspace or any explicit path they provide.
2. Run the bundled auditor script.
3. Read the Markdown report first, then inspect JSON only when exact details are needed.
4. If a patch is generated, show the user the patch path and summarize what it would change.
5. Do not apply patches automatically. Apply only after the user explicitly approves.

## Commands

Full audit:

```bash
python3 scripts/audit_skill_conflicts.py \
  --output-dir ./skill-conflict-auditor-report
```

Audit a new capability against installed packages:

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-capability /path/to/capability-or-SKILL.md \
  --output-dir ./skill-conflict-auditor-report
```

`--new-skill` is still supported as a compatibility alias. By default, `suggested_fixes.patch` only includes edits for the candidate package when `--new-capability` or `--new-skill` is provided. Installed files are reported but not patched. To generate patch suggestions for more files, pass `--patch-scope personal` or `--patch-scope all`.

Audit explicit roots:

```bash
python3 scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --root ~/.codex/plugins/cache \
  --root ~/.claude \
  --root ~/.openclaw \
  --root /path/to/project/skills-or-capabilities \
  --new-capability /path/to/new-capability \
  --output-dir ./skill-conflict-auditor-report
```

CI-style failure when high-severity findings exist:

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-capability /path/to/new-capability \
  --fail-on-high
```

## Conflict Types

The script checks for:

- Duplicate or near-duplicate package names.
- Missing or malformed `SKILL.md` frontmatter.
- Missing required `name` or `description`.
- Folder/name drift that may confuse users.
- Overlapping trigger descriptions.
- Broad descriptions that may steal tasks from more specific capabilities.
- Conflicting workflow policies, such as "ask first" versus "act directly".
- Tool preference conflicts, such as browser versus chrome or direct file editing versus generated images.
- Output contract conflicts, such as HTML report versus chat-only output.
- Missing referenced local resources.
- Suspiciously similar bundled script names.
- Candidate package conflicts against installed packages.

These checks are heuristic. Treat high-severity results as likely issues and medium/low findings as review prompts.

## Output

The auditor writes:

- `conflict_report.md`: human-readable findings and suggested actions.
- `conflict_report.json`: machine-readable findings, summaries, and scanned package metadata.
- `suggested_fixes.patch`: unified diff with conservative suggested edits.

## Patch Policy

The generated patch is intentionally conservative. It may:

- Add or repair missing frontmatter for a candidate package.
- Suggest a narrower `description`.
- Add a short `## Conflict Boundaries` section.
- Rename duplicate package names only when a deterministic suffix is safe.
- Add notes about missing resources instead of inventing files.

Never assume the patch is perfect. Review before applying.
