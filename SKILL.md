---
name: skill-conflict-auditor
description: Audit Codex skills for conflicts before or after installation. Use when checking installed skills, validating a newly written SKILL.md against existing skills, finding overlapping triggers or names, detecting malformed skill packages, or generating semi-automatic fix patches without applying them.
---

# Skill Conflict Auditor

Use this skill to inspect Codex skill packages for conflicts and produce a reviewable fix plan. It supports both:

- Full audit: scan all installed skills.
- Candidate audit: compare one new or edited skill against installed skills.

Default behavior is semi-automatic: generate reports and a patch file, but do not modify existing skills unless the user explicitly asks to apply a specific patch.

## Workflow

1. Identify scan roots.
   - Installed personal skills: `$CODEX_HOME/skills` or `~/.codex/skills`.
   - Installed plugin skills: `$CODEX_HOME/plugins/cache` or `~/.codex/plugins/cache`.
   - Current project skills: the user's workspace or any explicit path they provide.
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

Audit a new skill against installed skills:

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/skill-or-SKILL.md \
  --output-dir ./skill-conflict-auditor-report
```

By default, `suggested_fixes.patch` only includes edits for the candidate skill when `--new-skill` is provided. Installed skills are reported but not patched. To generate patch suggestions for more files, pass `--patch-scope personal` or `--patch-scope all`.

Audit explicit roots:

```bash
python3 scripts/audit_skill_conflicts.py \
  --root ~/.codex/skills \
  --root ~/.codex/plugins/cache \
  --root /path/to/project/skills \
  --new-skill /path/to/new-skill \
  --output-dir ./skill-conflict-auditor-report
```

CI-style failure when high-severity findings exist:

```bash
python3 scripts/audit_skill_conflicts.py \
  --new-skill /path/to/new-skill \
  --fail-on-high
```

## Conflict Types

The script checks for:

- Duplicate or near-duplicate skill names.
- Missing or malformed `SKILL.md` frontmatter.
- Missing required `name` or `description`.
- Folder/name drift that may confuse users.
- Overlapping trigger descriptions.
- Broad descriptions that may steal tasks from more specific skills.
- Conflicting workflow policies, such as "ask first" versus "act directly".
- Tool preference conflicts, such as browser versus chrome or direct file editing versus generated images.
- Output contract conflicts, such as HTML report versus chat-only output.
- Missing referenced local resources.
- Suspiciously similar bundled script names.
- Candidate skill conflicts against installed skills.

These checks are heuristic. Treat high-severity results as likely issues and medium/low findings as review prompts.

## Output

The auditor writes:

- `conflict_report.md`: human-readable findings and suggested actions.
- `conflict_report.json`: machine-readable findings, summaries, and scanned skill metadata.
- `suggested_fixes.patch`: unified diff with conservative suggested edits.

## Patch Policy

The generated patch is intentionally conservative. It may:

- Add or repair missing frontmatter for a candidate skill.
- Suggest a narrower `description`.
- Add a short `## Conflict Boundaries` section.
- Rename duplicate skill names only when a deterministic suffix is safe.
- Add notes about missing resources instead of inventing files.

Never assume the patch is perfect. Review before applying.
