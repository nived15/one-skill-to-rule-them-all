"""Shared storage and schema rules for the Copilot Task Observer."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any

import yaml

SCHEMA_VERSION = 1
STORE_REL = Path(".github") / "copilot-observations"
SKILL_DIR = Path(__file__).resolve().parent.parent
STATUSES = {"open", "actioned", "declined", "superseded", "parked"}
RESOLVED = {"actioned", "declined", "superseded"}
LEGACY_FIELDS = {"skill", "proposes_skill", "siblings_checked", "skill_qualifiers"}
BODY_LABELS = ("Issue", "Suggested improvement", "Principle")


class ObservationError(ValueError):
    """An invalid record or unsafe observer operation."""


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys rather than silently taking the last."""


def _unique_mapping(loader: UniqueLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ObservationError("YAML mapping keys must be scalars")
        if key in result:
            raise ObservationError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def parse_record(text: str) -> tuple[dict[str, Any], str]:
    text = text.removeprefix("\ufeff")
    match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", text, re.S)
    if not match:
        raise ObservationError("Missing or unclosed YAML frontmatter")
    try:
        data = yaml.load(match.group(1), Loader=UniqueLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise ObservationError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or any(not isinstance(key, str) for key in data):
        raise ObservationError("Frontmatter must be a mapping with string keys")
    return data, text[match.end():]


def read_record(path: Path) -> tuple[dict[str, Any], str]:
    return parse_record(Path(path).read_text(encoding="utf-8"))


def read_header(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8-sig") as stream:
        first = stream.readline()
        if first.rstrip("\r\n \t") != "---":
            raise ObservationError("Missing YAML frontmatter")
        lines = [first]
        for line in stream:
            lines.append(line)
            if line.rstrip("\r\n \t") == "---":
                return parse_record("".join(lines))[0]
    raise ObservationError("Unclosed YAML frontmatter")


def dump_record(data: dict[str, Any], body: str) -> str:
    header = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    return f"---\n{header}---\n{body}"


def resolve_workspace(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ObservationError(f"Workspace is not a directory: {root}")
    return root


def safe_relative_path(workspace: Path, relative: str, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ObservationError("Expected a nonempty workspace-relative path using '/' separators")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.drive or ".." in posix.parts or ":" in relative:
        raise ObservationError(f"Path escapes the workspace or is not relative: {relative}")
    root = Path(workspace).resolve(strict=True)
    target = (root / relative).resolve(strict=must_exist)
    if not target.is_relative_to(root) or target == root:
        raise ObservationError(f"Path escapes the workspace: {relative}")
    if must_exist and not target.is_file():
        raise ObservationError(f"Target is not a file: {relative}")
    return target


def iso_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return None
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def validate_record(
    data: dict[str, Any],
    body: str,
    workspace: Path | None = None,
    filename: str | None = None,
) -> list[str]:
    errors = []
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    identifier = data.get("id")
    if type(identifier) is not int or identifier < 1:
        errors.append("id must be a positive integer")
    if filename:
        match = re.fullmatch(r"(\d{4,})-[a-z0-9]+(?:-[a-z0-9]+)*\.md", filename)
        if not match or int(match.group(1)) != identifier:
            errors.append("filename must be NNNN-slug.md with the same id")
    for name in ("title", "area", "session_context", "related_targets_checked"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            errors.append(f"{name} must be a nonempty string")
    status = data.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("status must be open, actioned, declined, superseded, or parked")
    if data.get("type") not in ("open-source", "internal"):
        errors.append("type must be open-source or internal")
    logged = iso_date(data.get("date"))
    if logged is None:
        errors.append("date must be a valid YYYY-MM-DD")
    for name in ("targets", "proposed_workflows"):
        value = data.get(name)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append(f"{name} must be a list of nonempty strings")
        elif len(value) != len(set(value)):
            errors.append(f"{name} must not contain duplicates")
    if not data.get("targets") and not data.get("proposed_workflows") and not data.get("migration_note"):
        errors.append("a record must name targets or proposed_workflows")
    targets = data.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, str):
                continue
            try:
                safe_relative_path(
                    workspace or SKILL_DIR, target,
                    must_exist=workspace is not None and status not in tuple(RESOLVED),
                )
            except (ObservationError, OSError) as exc:
                errors.append(f"target {target!r}: {exc}")
    condition = data.get("parked_until")
    if status == "parked":
        if not isinstance(condition, str) or not condition.strip():
            errors.append("parked observations require parked_until")
    elif condition not in (None, ""):
        errors.append("parked_until must be empty unless status is parked")
    if isinstance(status, str) and status in RESOLVED:
        resolved = iso_date(data.get("resolved"))
        if resolved is None:
            errors.append("resolved observations require a valid resolved date")
        elif logged and resolved < logged:
            errors.append("resolved date cannot precede date")
        if not isinstance(data.get("resolution"), str) or not data["resolution"].strip():
            errors.append("resolved observations require a resolution")
    elif data.get("resolved") not in (None, "") or data.get("resolution") not in (None, ""):
        errors.append("unresolved observations must not carry resolved or resolution values")
    for label in BODY_LABELS:
        match = re.search(rf"(?ms)^\*\*{re.escape(label)}:\*\*\s*(.*?)(?=^\*\*[^*\n]+:\*\*|\Z)", body)
        if not match or not match.group(1).strip():
            errors.append(f"body requires a nonempty **{label}:** section")
    for field in sorted(LEGACY_FIELDS & data.keys()):
        errors.append(f"legacy field {field} requires migration")
    for field in ("shared_for_review", "sanitized"):
        if field in data and type(data[field]) is not bool:
            errors.append(f"{field} must be a boolean")
    if "target_qualifiers" in data and not isinstance(data["target_qualifiers"], dict):
        errors.append("target_qualifiers must be a mapping")
    if data.get("migration_note") is not None and not isinstance(data["migration_note"], str):
        errors.append("migration_note must be a string")
    reference = data.get("reference")
    if reference not in (None, ""):
        if not isinstance(reference, str):
            errors.append("reference must be a workspace-relative path string")
        else:
            try:
                safe_relative_path(workspace or SKILL_DIR, reference, must_exist=workspace is not None)
            except (ObservationError, OSError) as exc:
                errors.append(f"reference: {exc}")
    return errors


def exclusive_write(path: Path, text: str) -> None:
    """Create a file without clobbering another writer's record."""
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="") as stream:
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        except OSError:
            stream.close()
            path.unlink()
            raise


def atomic_write(path: Path, text: str) -> None:
    """Replace managed state only; callers must hold the store lock."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
