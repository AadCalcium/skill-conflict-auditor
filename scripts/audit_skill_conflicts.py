#!/usr/bin/env python3
"""Audit Codex skills for conflicts and generate reports plus a review patch."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "codex", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "skill", "skills", "the",
    "this", "to", "use", "used", "user", "users", "when", "with", "you",
    "your", "帮我", "使用", "用于", "当用户", "用户", "进行", "生成", "创建",
}

STRONG_BROAD_WORDS = {
    "anything", "all", "everything", "general", "universal", "always",
    "任何", "所有", "全部", "通用", "总是", "一切",
}

WEAK_BROAD_WORDS = {"any", "every", "whenever"}

ASK_FIRST_PATTERNS = [
    r"\bask\b.*\bfirst\b",
    r"\bconfirm\b.*\bbefore\b",
    r"\bclarify\b.*\bbefore\b",
    r"先问",
    r"先确认",
    r"等待用户",
]

ACT_DIRECTLY_PATTERNS = [
    r"\bdirectly\b",
    r"\bwithout\b.*\basking\b",
    r"\bdo not ask\b",
    r"\bnever ask\b",
    r"直接执行",
    r"无需确认",
    r"不要询问",
]

TOOL_GROUPS = {
    "browser": [r"\bbrowser\b", r"\bin-app browser\b", r"浏览器"],
    "chrome": [r"\bchrome\b", r"用户.*cookies", r"登录态"],
    "image_gen": [r"\bimage generation\b", r"\bgenerate image\b", r"生成图片", r"出图"],
    "figma": [r"\bfigma\b"],
    "github": [r"\bgithub\b", r"\bpull request\b", r"\bissue\b"],
    "documents": [r"\bdocx\b", r"\bword\b", r"文档"],
    "spreadsheets": [r"\bxlsx\b", r"\bcsv\b", r"表格"],
    "presentations": [r"\bpptx\b", r"\bpowerpoint\b", r"幻灯片"],
}

OUTPUT_PATTERNS = {
    "html": [r"\bhtml\b", r"网页报告", r"可视化报告"],
    "markdown": [r"\bmarkdown\b", r"\bmd\b", r"聊天框", r"直接展示"],
    "json": [r"\bjson\b", r"机器可读"],
    "image": [r"\bpng\b", r"\bjpg\b", r"图片"],
}


@dataclass
class Skill:
    path: str
    dir: str
    name: str = ""
    description: str = ""
    body: str = ""
    frontmatter: dict[str, str] = field(default_factory=dict)
    frontmatter_raw: str = ""
    parse_errors: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    output_contracts: list[str] = field(default_factory=list)
    workflow_flags: list[str] = field(default_factory=list)
    resource_refs: list[str] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)
    script_names: list[str] = field(default_factory=list)
    is_candidate: bool = False


@dataclass
class Finding:
    severity: str
    kind: str
    title: str
    detail: str
    skills: list[str]
    recommendation: str


def normalize_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    return value.strip("-")


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    result = []
    for word in words:
        word = word.strip("-_")
        if word and word not in STOPWORDS and len(word) > 1:
            result.append(word)
    return sorted(set(result))


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def read_skill(path: Path, candidate_paths: set[Path]) -> Skill:
    skill_path = path if path.name == "SKILL.md" else path / "SKILL.md"
    skill = Skill(path=str(skill_path), dir=str(skill_path.parent))
    skill.is_candidate = any(skill_path == p or skill_path.parent == p for p in candidate_paths)

    try:
        text = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = skill_path.read_text(encoding="utf-8", errors="replace")
        skill.parse_errors.append("File is not clean UTF-8; replacement characters were used.")
    except OSError as exc:
        skill.parse_errors.append(f"Cannot read SKILL.md: {exc}")
        return skill

    frontmatter, body, errors, raw = parse_frontmatter(text)
    skill.frontmatter = frontmatter
    skill.frontmatter_raw = raw
    skill.body = body
    skill.parse_errors.extend(errors)
    skill.name = frontmatter.get("name", "").strip()
    skill.description = frontmatter.get("description", "").strip()
    skill.tokens = tokenize(" ".join([skill.name, skill.description, body[:4000]]))
    skill.tools = detect_groups(text, TOOL_GROUPS)
    skill.output_contracts = detect_groups(text, OUTPUT_PATTERNS)
    skill.workflow_flags = detect_workflow_flags(text)
    skill.resource_refs = find_local_refs(body)
    skill.missing_refs = missing_refs(skill_path.parent, skill.resource_refs)
    scripts_dir = skill_path.parent / "scripts"
    if scripts_dir.is_dir():
        skill.script_names = sorted(p.name for p in scripts_dir.iterdir() if p.is_file())
    return skill


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str], str]:
    errors: list[str] = []
    if not text.startswith("---\n"):
        return {}, text, ["Missing YAML frontmatter block starting with ---."], ""
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text, ["Frontmatter block is not closed with ---."], ""
    raw = text[4:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")
    data: dict[str, str] = {}
    current_key = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s", line) and current_key:
            data[current_key] = (data[current_key] + " " + line.strip()).strip()
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            errors.append(f"Cannot parse frontmatter line: {line}")
            continue
        key, value = match.groups()
        current_key = key
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        data[key] = value
    if "name" not in data:
        errors.append("Missing required frontmatter field: name.")
    if "description" not in data:
        errors.append("Missing required frontmatter field: description.")
    return data, body, errors, raw


def detect_groups(text: str, groups: dict[str, list[str]]) -> list[str]:
    found = []
    for name, patterns in groups.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                found.append(name)
                break
    return sorted(found)


def detect_workflow_flags(text: str) -> list[str]:
    flags = []
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in ASK_FIRST_PATTERNS):
        flags.append("ask-first")
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in ACT_DIRECTLY_PATTERNS):
        flags.append("act-directly")
    return flags


def find_local_refs(body: str) -> list[str]:
    refs = set()
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body):
        ref = clean_resource_ref(match.group(1).split("#", 1)[0])
        if is_placeholder_ref(ref):
            continue
        if is_bundled_resource_ref(ref):
            refs.add(ref)
    for match in re.finditer(r"`((?:scripts|references|assets)/[^`]+)`", body):
        ref = clean_resource_ref(match.group(1))
        if not is_placeholder_ref(ref):
            refs.add(ref)
    return sorted(refs)


def clean_resource_ref(ref: str) -> str:
    ref = ref.strip().strip("<>")
    return re.split(r"\s+", ref, maxsplit=1)[0]


def is_bundled_resource_ref(ref: str) -> bool:
    return bool(ref) and not re.match(r"^[a-z]+://", ref) and ref.startswith(("scripts/", "references/", "assets/"))


def is_placeholder_ref(ref: str) -> bool:
    return (
        bool(re.fullmatch(r"[A-Z_]+", ref))
        or "{" in ref
        or "}" in ref
        or "<" in ref
        or ">" in ref
        or ref.startswith(("path/to/", "src/components/"))
    )


def missing_refs(base: Path, refs: Iterable[str]) -> list[str]:
    missing = []
    for ref in refs:
        if ref.startswith("/") or ".." in Path(ref).parts:
            continue
        if not (base / ref).exists():
            missing.append(ref)
    return missing


def discover_skill_paths(roots: list[Path], new_skill: Path | None) -> list[Path]:
    paths: set[Path] = set()
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        if root.is_file() and root.name == "SKILL.md":
            paths.add(root.resolve())
            continue
        if (root / "SKILL.md").exists():
            paths.add((root / "SKILL.md").resolve())
        for skill_file in root.rglob("SKILL.md"):
            paths.add(skill_file.resolve())
    if new_skill:
        target = new_skill.expanduser()
        if target.is_file():
            paths.add(target.resolve())
        elif (target / "SKILL.md").exists():
            paths.add((target / "SKILL.md").resolve())
    return sorted(paths)


def default_roots() -> list[Path]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    roots = [codex_home / "skills", codex_home / "plugins" / "cache"]
    cwd = Path.cwd()
    if (cwd / "SKILL.md").exists() or any(cwd.glob("*/SKILL.md")):
        roots.append(cwd)
    return roots


def audit(skills: list[Skill]) -> list[Finding]:
    findings: list[Finding] = []
    by_name: dict[str, list[Skill]] = {}

    for skill in skills:
        label = skill_label(skill)
        for error in skill.parse_errors:
            findings.append(Finding(
                "high", "schema", "Invalid skill metadata", error, [label],
                "Repair frontmatter so it has valid YAML-style name and description fields.",
            ))
        if skill.name:
            by_name.setdefault(normalize_name(skill.name), []).append(skill)
        folder_name = normalize_name(Path(skill.dir).name)
        skill_name = normalize_name(skill.name)
        if skill.name and folder_name and skill_name and folder_name != skill_name:
            similarity = jaccard(folder_name.split("-"), skill_name.split("-"))
            if similarity < 0.5:
                findings.append(Finding(
                    "low", "naming", "Folder name differs from skill name",
                    f"Folder `{Path(skill.dir).name}` does not closely match frontmatter name `{skill.name}`.",
                    [label],
                    "Consider aligning the folder name and skill name for easier maintenance.",
                ))
        if skill.description:
            desc_tokens = tokenize(skill.description)
            strong_hits = sorted(set(desc_tokens) & STRONG_BROAD_WORDS)
            weak_hits = sorted(set(desc_tokens) & WEAK_BROAD_WORDS)
            too_broad = bool(strong_hits) or len(weak_hits) >= 2 or len(desc_tokens) < 5
            if too_broad:
                findings.append(Finding(
                    "medium", "trigger-breadth", "Description may be too broad",
                    f"Description has broad or sparse trigger language: {', '.join(strong_hits + weak_hits) or 'too few distinctive terms'}.",
                    [label],
                    "Narrow the description to specific task types, inputs, outputs, and exclusions.",
                ))
        if skill.missing_refs:
            findings.append(Finding(
                "medium", "resources", "Referenced resources are missing",
                "Missing local references: " + ", ".join(f"`{ref}`" for ref in skill.missing_refs),
                [label],
                "Create the missing files or remove/update the references.",
            ))

    for name, group in by_name.items():
        if len(group) > 1:
            findings.append(Finding(
                "high", "duplicate-name", "Duplicate skill name",
                f"Multiple skills normalize to `{name}`.",
                [skill_label(s) for s in group],
                "Rename one skill and update its description so trigger intent is distinct.",
            ))

    for i, left in enumerate(skills):
        for right in skills[i + 1 :]:
            if not should_compare(left, right):
                continue
            pair_labels = [skill_label(left), skill_label(right)]
            name_score = jaccard(tokenize(left.name), tokenize(right.name))
            desc_score = jaccard(tokenize(left.description), tokenize(right.description))
            body_score = jaccard(left.tokens, right.tokens)
            if (
                name_score >= 0.8
                and left.name
                and right.name
                and normalize_name(left.name) != normalize_name(right.name)
            ):
                findings.append(Finding(
                    "high", "near-duplicate-name", "Near-duplicate skill names",
                    f"Name similarity score: {name_score:.2f}.",
                    pair_labels,
                    "Rename or merge skills if they represent the same capability.",
                ))
            if desc_score >= 0.42 or body_score >= 0.34:
                findings.append(Finding(
                    "medium", "trigger-overlap", "Overlapping trigger language",
                    f"Description similarity: {desc_score:.2f}; overall token similarity: {body_score:.2f}.",
                    pair_labels,
                    "Add clearer boundaries to each description and document which skill wins for shared terms.",
                ))
            shared_tools = sorted(set(left.tools) & set(right.tools))
            if shared_tools and (desc_score >= 0.25 or body_score >= 0.25):
                findings.append(Finding(
                    "low", "tool-overlap", "Similar skills mention the same tools",
                    "Shared tool groups: " + ", ".join(shared_tools),
                    pair_labels,
                    "Confirm whether both skills should own this tool workflow or whether one should defer.",
                ))
            workflow_conflict = (
                ("ask-first" in left.workflow_flags and "act-directly" in right.workflow_flags)
                or ("act-directly" in left.workflow_flags and "ask-first" in right.workflow_flags)
            )
            if workflow_conflict and (desc_score >= 0.2 or body_score >= 0.2):
                findings.append(Finding(
                    "medium", "workflow-policy", "Workflow policies may conflict",
                    f"Workflow flags: {left.workflow_flags} vs {right.workflow_flags}.",
                    pair_labels,
                    "Clarify whether the user should be asked before execution for this task family.",
                ))
            shared_outputs = sorted(set(left.output_contracts) & set(right.output_contracts))
            different_outputs = sorted(set(left.output_contracts) ^ set(right.output_contracts))
            if shared_outputs and different_outputs and (desc_score >= 0.25 or body_score >= 0.25):
                findings.append(Finding(
                    "low", "output-contract", "Similar skills have different output contracts",
                    f"Shared outputs: {shared_outputs}; differing outputs: {different_outputs}.",
                    pair_labels,
                    "Document output precedence or split trigger descriptions by final artifact type.",
                ))
            shared_scripts = sorted(set(left.script_names) & set(right.script_names))
            if shared_scripts and (desc_score >= 0.2 or body_score >= 0.2):
                findings.append(Finding(
                    "low", "script-overlap", "Similar skills include same script names",
                    "Shared script file names: " + ", ".join(shared_scripts),
                    pair_labels,
                    "Check whether duplicated scripts should be shared, renamed, or kept intentionally separate.",
                ))
    return sorted(findings, key=lambda f: severity_rank(f.severity))


def should_compare(left: Skill, right: Skill) -> bool:
    if left.path == right.path:
        return False
    candidates = [s for s in (left, right) if s.is_candidate]
    if candidates:
        return True
    return True


def severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def skill_label(skill: Skill) -> str:
    name = skill.name or Path(skill.dir).name
    marker = "candidate " if skill.is_candidate else ""
    return f"{marker}{name} ({skill.path})"


def should_patch_skill(skill: Skill, patch_scope: str) -> bool:
    if patch_scope == "all":
        return True
    if patch_scope == "candidate":
        return skill.is_candidate
    if patch_scope == "personal":
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
        try:
            skill_path = Path(skill.path).resolve()
            personal_root = (codex_home / "skills").resolve()
            return skill.is_candidate or skill_path.is_relative_to(personal_root)
        except OSError:
            return skill.is_candidate
    return False


def suggested_text(skill: Skill, findings: list[Finding], patch_scope: str) -> str | None:
    if not should_patch_skill(skill, patch_scope):
        return None
    path = Path(skill.path)
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        return None

    relevant = [f for f in findings if any(skill.path in item for item in f.skills)]
    if not relevant:
        return None

    text = original
    if "Missing YAML frontmatter block starting with ---." in skill.parse_errors:
        name = normalize_name(Path(skill.dir).name) or "new-skill"
        description = "TODO: Describe the exact tasks, inputs, outputs, and boundaries for this skill."
        text = f"---\nname: {name}\ndescription: {description}\n---\n\n{text}"
    elif "Missing required frontmatter field: name." in skill.parse_errors or "Missing required frontmatter field: description." in skill.parse_errors:
        insert_lines = []
        if "Missing required frontmatter field: name." in skill.parse_errors:
            insert_lines.append(f"name: {normalize_name(Path(skill.dir).name) or 'new-skill'}")
        if "Missing required frontmatter field: description." in skill.parse_errors:
            insert_lines.append("description: TODO: Describe the exact tasks, inputs, outputs, and boundaries for this skill.")
        text = text.replace("---\n", "---\n" + "\n".join(insert_lines) + "\n", 1)

    if skill.description and any(f.kind in {"trigger-overlap", "trigger-breadth"} for f in relevant):
        boundary = (
            "\n## Conflict Boundaries\n\n"
            "- Prefer this skill only for the task family named in the frontmatter description.\n"
            "- If another installed skill has a more specific description for the user's request, use the more specific skill.\n"
            "- When trigger intent is ambiguous, report the overlap and ask before applying changes.\n"
        )
        if "## Conflict Boundaries" not in text:
            text = text.rstrip() + boundary + "\n"
    return text if text != original else None


def generate_patch(skills: list[Skill], findings: list[Finding], patch_scope: str) -> str:
    chunks = []
    for skill in skills:
        revised = suggested_text(skill, findings, patch_scope)
        if revised is None:
            continue
        path = Path(skill.path)
        try:
            original = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            continue
        updated = revised.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original,
            updated,
            fromfile=str(path),
            tofile=str(path),
        )
        chunk = "".join(diff)
        if chunk:
            chunks.append(chunk)
    return "\n".join(chunks)


def write_reports(out_dir: Path, skills: list[Skill], findings: list[Finding], patch: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "conflict_report.json").write_text(
        json.dumps(
            {
                "summary": summarize(findings),
                "findings": [asdict(f) for f in findings],
                "skills": [asdict(s) for s in skills],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "conflict_report.md").write_text(markdown_report(skills, findings, patch), encoding="utf-8")
    (out_dir / "suggested_fixes.patch").write_text(patch, encoding="utf-8")


def summarize(findings: list[Finding]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0, "total": len(findings)}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


def markdown_report(skills: list[Skill], findings: list[Finding], patch: str) -> str:
    counts = summarize(findings)
    lines = [
        "# Skill Conflict Audit Report",
        "",
        "## Summary",
        "",
        f"- Skills scanned: {len(skills)}",
        f"- Findings: {counts['total']} total, {counts['high']} high, {counts['medium']} medium, {counts['low']} low",
        f"- Suggested patch: {'generated' if patch.strip() else 'empty'}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No conflicts found by the current heuristic checks.")
    for index, finding in enumerate(findings, 1):
        lines.extend([
            f"### {index}. [{finding.severity.upper()}] {finding.title}",
            "",
            f"- Kind: `{finding.kind}`",
            f"- Detail: {finding.detail}",
            "- Skills:",
        ])
        lines.extend(f"  - `{skill}`" for skill in finding.skills)
        lines.extend([
            f"- Recommendation: {finding.recommendation}",
            "",
        ])
    lines.extend([
        "## Scanned Skills",
        "",
    ])
    for skill in skills:
        lines.extend([
            f"- `{skill.name or Path(skill.dir).name}`",
            f"  - Path: `{skill.path}`",
            f"  - Candidate: `{str(skill.is_candidate).lower()}`",
            f"  - Tools: `{', '.join(skill.tools) or 'none'}`",
            f"  - Outputs: `{', '.join(skill.output_contracts) or 'none'}`",
        ])
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[], help="Skill root to scan. Can be repeated.")
    parser.add_argument("--new-skill", help="Path to a candidate skill directory or SKILL.md.")
    parser.add_argument("--output-dir", default="./skill-conflict-auditor-report", help="Directory for reports.")
    parser.add_argument(
        "--patch-scope",
        choices=["candidate", "personal", "all"],
        default="candidate",
        help="Which skills may appear in suggested_fixes.patch. Default: candidate.",
    )
    parser.add_argument("--fail-on-high", action="store_true", help="Exit 1 when high-severity findings exist.")
    args = parser.parse_args(argv)

    roots = [Path(root) for root in args.root] if args.root else default_roots()
    new_skill = Path(args.new_skill) if args.new_skill else None
    candidate_paths: set[Path] = set()
    if new_skill:
        candidate_paths.add(new_skill.expanduser().resolve())
        if new_skill.expanduser().is_dir():
            candidate_paths.add((new_skill.expanduser() / "SKILL.md").resolve())

    skill_paths = discover_skill_paths(roots, new_skill)
    skills = [read_skill(path, candidate_paths) for path in skill_paths]
    findings = audit(skills)
    patch = generate_patch(skills, findings, args.patch_scope)
    out_dir = Path(args.output_dir)
    write_reports(out_dir, skills, findings, patch)

    counts = summarize(findings)
    print(f"Scanned {len(skills)} skills.")
    print(f"Findings: {counts['total']} total, {counts['high']} high, {counts['medium']} medium, {counts['low']} low.")
    print(f"Markdown report: {out_dir / 'conflict_report.md'}")
    print(f"JSON report: {out_dir / 'conflict_report.json'}")
    print(f"Suggested patch: {out_dir / 'suggested_fixes.patch'}")
    return 1 if args.fail_on_high and counts["high"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
