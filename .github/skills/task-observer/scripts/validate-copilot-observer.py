"""Validate a native Copilot observer installation and its local records."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from observer_common import (
    ObservationError, STORE_REL, iso_date,
    read_record, resolve_workspace, validate_record,
)
from observer import entry_paths, highest_id, store_path

SKILL_REL = Path(".github") / "skills" / "task-observer"
REFERENCES = (
    "environments", "migration", "observation-log", "signals",
    "skill-authoring", "starter-principles", "weekly-review",
)
PROMPTS = ("observer-start", "observer-review", "observer-apply")
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def strip_fences(text: str) -> str:
    return re.sub(r"(?ms)^([`~]{3,})[^\n]*\n.*?^\1[ \t]*(?:\n|\Z)", "", text)


def validate_links(path: Path, workspace: Path) -> list[str]:
    errors = []
    text = strip_fences(path.read_text(encoding="utf-8"))
    for raw in LINK.findall(text):
        if raw.startswith(("#", "https://", "http://", "mailto:")):
            continue
        target = unquote(raw.split("#", 1)[0])
        if not target or "<" in target:
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.is_relative_to(workspace) or not resolved.exists():
            errors.append(f"{path.relative_to(workspace)}: broken local link {raw}")
    if re.search(r"(?m)^(<<<<<<< |=======$|>>>>>>> )", text):
        errors.append(f"{path.relative_to(workspace)}: merge conflict marker")
    return errors


def validate_workspace(workspace: Path) -> list[str]:
    errors = []
    skill = workspace / SKILL_REL
    required = [
        workspace / ".github" / "copilot-instructions.md",
        skill / "SKILL.md", skill / "requirements.txt",
        *[skill / "references" / f"{name}.md" for name in REFERENCES],
        *[skill / "scripts" / name for name in (
            "observer.py", "observer_common.py", "migrate-log.py",
            "validate-copilot-observer.py", "review.py",
        )],
        *[workspace / ".github" / "prompts" / f"{name}.prompt.md" for name in PROMPTS],
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"Required file missing: {path.relative_to(workspace)}")
        elif path.is_symlink() or not path.resolve().is_relative_to(workspace):
            errors.append(f"Linked installation resource is not allowed: {path.relative_to(workspace)}")
    legacy_paths = (
        "SKILL.md", "scripts/migrate-log.py", "scripts/validate-skill-bundle.py",
        ".github/workflows/release-bundle.yml", ".github/workflows/tessl-publish.yml",
        ".tessl-plugin/plugin.json",
    )
    for old in legacy_paths:
        path = workspace / old
        if path.is_file():
            errors.append(f"Obsolete root resource or publishing configuration remains: {old}")
    specification = skill / "SKILL.md"
    if specification.is_file():
        try:
            metadata, _ = read_record(specification)
            if metadata.get("name") != skill.name:
                errors.append("Native skill name must match task-observer directory")
            if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
                errors.append("Native skill description must be a nonempty string")
        except (ObservationError, OSError) as exc:
            errors.append(f"SKILL.md: {exc}")
    bootstrap = workspace / ".github" / "copilot-instructions.md"
    if bootstrap.is_file() and "skills/task-observer/SKILL.md" not in bootstrap.read_text(encoding="utf-8"):
        errors.append("Bootstrap must reference the native task-observer skill")
    for prompt in sorted((workspace / ".github" / "prompts").glob("*.prompt.md")):
        try:
            metadata, body = read_record(prompt)
            if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
                errors.append(f"{prompt.name}: description is required by this project")
            if "mode" in metadata or "applyTo" in metadata:
                errors.append(f"{prompt.name}: use agent, not mode; applyTo belongs in instructions")
            if metadata.get("agent", "agent") not in ("agent", "ask", "plan"):
                errors.append(f"{prompt.name}: unsupported shared prompt agent")
            if prompt.stem.removesuffix(".prompt") in PROMPTS and "../skills/task-observer/" not in body:
                errors.append(f"{prompt.name}: missing native skill reference")
        except (ObservationError, OSError) as exc:
            errors.append(f"{prompt.name}: {exc}")
    for instructions in (workspace / ".github" / "instructions").glob("*.instructions.md"):
        try:
            metadata, _ = read_record(instructions)
            if not isinstance(metadata.get("applyTo"), str) or not metadata["applyTo"].strip():
                errors.append(f"{instructions.name}: scoped instructions require applyTo")
        except (ObservationError, OSError) as exc:
            errors.append(f"{instructions.name}: {exc}")
    documents = list(workspace.glob("*.md"))
    documents += list(skill.rglob("*.md"))
    documents += list((workspace / ".github" / "prompts").glob("*.md"))
    documents += list((workspace / ".github" / "instructions").glob("*.md"))
    documents += [path for path in (bootstrap, workspace / STORE_REL / "README.md") if path.is_file()]
    for document in documents:
        try:
            errors.extend(validate_links(document, workspace))
        except (OSError, UnicodeError) as exc:
            errors.append(f"{document}: {exc}")
    try:
        store = store_path(workspace)
        if (store / "observation-log").exists():
            for path in entry_paths(store, include_archive=True):
                try:
                    metadata, body = read_record(path)
                    errors.extend(f"{path.name}: {error}" for error in
                                  validate_record(metadata, body, workspace, path.name))
                    if metadata.get("migration_note"):
                        errors.append(f"{path.name}: unresolved migration_note")
                except (ObservationError, OSError) as exc:
                    errors.append(f"{path.name}: {exc}")
            floor = highest_id(store)
            recorded = store / "observation-log" / "archive" / ".id-floor"
            if int(recorded.read_text(encoding="ascii").strip()) < floor:
                errors.append(".id-floor is below the highest issued observation ID")
            state_files = (store / "last-review-date.txt", store / "cross-cutting-principles.md")
            if any(path.is_symlink() for path in state_files):
                raise ObservationError("Linked observer state files are not allowed")
            marker = state_files[0].read_text(encoding="utf-8").strip()
            if marker != "never" and iso_date(marker) is None:
                errors.append("last-review-date.txt must be never or a valid YYYY-MM-DD")
            if not (store / "cross-cutting-principles.md").is_file():
                errors.append("cross-cutting-principles.md is missing")
    except (ObservationError, OSError, ValueError) as exc:
        errors.append(f"Observation store: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Repository/folder root, not skill directory")
    args = parser.parse_args(argv)
    try:
        errors = validate_workspace(resolve_workspace(args.workspace))
    except (ObservationError, OSError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Copilot observer workspace is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
