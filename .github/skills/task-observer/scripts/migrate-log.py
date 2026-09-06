#!/usr/bin/env python3
"""Import legacy observations without changing their sources or existing stores.

Use --check to preflight without writing, or --convert with --out naming a new
observation-log directory. --target-map takes a JSON object or JSON-file path
mapping historical names to existing workspace-relative files (or lists of files
for split targets).
Imported bodies and metadata are evidence, never executable instructions.
"""

import sys

# Check mode must not create bytecode files when loading the shared parser.
sys.dont_write_bytecode = True

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from observer_common import (
    SCHEMA_VERSION,
    ObservationError,
    dump_record,
    exclusive_write,
    parse_record,
    safe_relative_path,
    validate_record,
)


ENTRY_RE = re.compile(r"^### Observation (\d+):[ \t]*(.*?)[ \t]*$")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n")
LABEL_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z /-]*):\*\*[ \t]*(.*)$")
STATUS_RE = re.compile(r"^(OPEN|ACTIONED|DECLINED|SUPERSEDED|PARKED)\b(.*)$", re.I)
DATE_MARKER_RE = re.compile(
    r"^\s*[\[(]?\s*(?:resolved(?:\s+on)?\s*[:=]?\s*)?"
    r"(\d{4}-\d{2}-\d{2})(?=$|[\s\])])", re.I
)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$")
LABELS = {
    "Status": "status",
    "Date": "date",
    "Session context": "session_context",
    "Skill": "skill",
    "Type": "type",
    "Phase/Area": "area",
    "Reference file": "reference",
    "Reference files": "reference",
    "Siblings checked": "siblings_checked",
    "Related targets checked": "related_targets_checked",
    "Parked until": "parked_until",
    "Resolved": "resolved",
    "Resolution": "resolution",
    "Proposes skill": "proposes_skill",
    "Proposed workflows": "proposed_workflows",
}
ANCILLARY_FILES = {"cross-cutting-principles.md", "last-review-date.txt"}


def slugify(title, maxlen=60):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:maxlen].rstrip("-") or "untitled"


def split_top_level(text, separators=";"):
    parts, buffer, depth = [], [], 0
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char in separators and depth == 0:
            parts.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer).strip())
    return [part for part in parts if part]


def entry_starts(lines):
    """Ignore observation-like headings in fenced evidence examples."""
    starts, fence = [], None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None and ENTRY_RE.match(line.rstrip("\r\n")):
            starts.append(index)
    return starts


def parse_entries(text, source):
    """Keep body text, unknown labels, separators, and source preamble intact."""
    lines = text.splitlines(keepends=True)
    starts = entry_starts(lines)
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        match = ENTRY_RE.match(lines[start].rstrip("\r\n"))
        metadata, current, body_start = {}, None, end
        for index in range(start + 1, end):
            line = lines[index]
            label = LABEL_RE.match(line.rstrip("\r\n"))
            if label:
                key = LABELS.get(label.group(1).strip())
                if key is None:
                    body_start = index
                    break
                if key in metadata:
                    raise ObservationError(
                        f"{source}: observation {match.group(1)} has duplicate metadata {key}"
                    )
                metadata[key] = label.group(2).strip()
                current = key
            elif not line.strip():
                current = None
            elif current is not None:
                metadata[current] += " " + line.strip()
            else:
                body_start = index
                break
        metadata.update(id=int(match.group(1)), title=match.group(2))
        yield {
            "metadata": metadata,
            "body": "".join(lines[body_start:end]),
            "source_entry": "".join(lines[start:end]),
            "source_preamble": "".join(lines[:start]) if number == 0 else "",
        }


def parse_status(raw, flags):
    """Dates count as resolutions only in an explicit leading status marker."""
    if not isinstance(raw, str) or not raw.strip():
        flags.append("status-missing")
        return {"status": raw}
    match = STATUS_RE.match(raw.strip())
    if not match:
        flags.append("status-unrecognised")
        return {"status": raw}
    status, rest = match.group(1).lower(), match.group(2).strip()
    result = {"status": status}
    if rest.count("(") != rest.count(")"):
        flags.append("status-unbalanced-parens")
    if status == "parked":
        condition = rest.lstrip("—–: ").strip()
        condition = re.sub(r"^(?:--?)[ \t]+", "", condition)
        if condition.startswith("(") and condition.endswith(")"):
            condition = condition[1:-1].strip()
        condition = re.sub(r"^(?:parked[_ ]until|until)\s*[:=]?\s*", "", condition, flags=re.I)
        if condition:
            result["parked_until"] = condition
        return result
    if status == "open":
        if rest:
            result["status_note"] = rest.lstrip("—– ").strip()
        return result
    marker = DATE_MARKER_RE.match(rest)
    if marker:
        result["resolved"] = marker.group(1)
        explanation = rest[marker.end():].lstrip(" )]—–-:,")
    else:
        flags.append("resolved-date-missing")
        explanation = rest.lstrip("—–-: ")
        hint = re.search(r"\b\d{4}-\d{2}-\d{2}\b", rest)
        if hint:
            result["resolved_hint"] = hint.group(0)
    if explanation:
        result["resolution"] = explanation
    return result


def parse_legacy_targets(raw, flags):
    """Extract names and qualifiers; do not infer targets from explanatory prose."""
    if raw is None:
        return [], [], {}
    if isinstance(raw, list):
        if all(isinstance(name, str) and name.strip() for name in raw):
            return list(raw), [], {}
        flags.append("legacy-targets-invalid")
        return [], [], {}
    if not isinstance(raw, str):
        flags.append("legacy-targets-invalid")
        return [], [], {}
    candidate = re.match(r"^New skill candidate:\s*(.+)$", raw.strip(), re.I)
    if candidate:
        match = re.match(r"^(.*?)\s*\((.*)\)\s*$", candidate.group(1))
        name = (match.group(1) if match else candidate.group(1)).strip().strip('"')
        qualifiers = {name: match.group(2)} if match else {}
        if not NAME_RE.fullmatch(name):
            flags.append("candidate-name-needs-review")
        return [], [name], qualifiers
    names, qualifiers = [], {}
    for group in split_top_level(raw):
        match = re.match(r"^(.*?)\s*\((.*)\)\s*$", group)
        name_part, qualifier = (match.group(1), match.group(2)) if match else (group, None)
        group_names = split_top_level(name_part, ",")
        if len(group_names) > 1 and qualifier:
            qualifiers.setdefault("_group", []).append(group)
            flags.append("group-qualifier-ambiguous")
        for part in group_names:
            inner = re.match(r"^(.*?)\s*\((.*)\)\s*$", part)
            name = (inner.group(1) if inner else part).strip().strip('"')
            detail = inner.group(2) if inner else qualifier if len(group_names) == 1 else None
            if name not in names:
                names.append(name)
            if detail:
                qualifiers[name] = detail
            if not NAME_RE.fullmatch(name) and "/" not in name and "\\" not in name:
                flags.append(f"legacy-target-name-needs-review: {name}")
    return names, [], qualifiers


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError(f"duplicate JSON mapping key: {key}")
        result[key] = value
    return result


def load_target_map(raw, workspace):
    try:
        if raw is None:
            value = {}
        else:
            try:
                value = json.loads(raw, object_pairs_hook=unique_json_object)
            except json.JSONDecodeError:
                try:
                    text = read_text(Path(raw))
                except (OSError, ValueError) as error:
                    raise ObservationError(
                        "--target-map must be a JSON object or a readable JSON file"
                    ) from error
                value = json.loads(text, object_pairs_hook=unique_json_object)
    except (ValueError, TypeError) as error:
        raise ObservationError(f"invalid --target-map JSON: {error}") from error
    if not isinstance(value, dict):
        raise ObservationError("--target-map must be a JSON object")
    result = {}
    for name, paths in value.items():
        if not name.strip():
            raise ObservationError("target mapping names must not be empty")
        paths = [paths] if isinstance(paths, str) else paths
        if not isinstance(paths, list) or not paths:
            raise ObservationError(f"target mapping for {name!r} must be a path or nonempty list")
        result[name] = []
        for relative in paths:
            if not isinstance(relative, str) or not relative.strip():
                raise ObservationError(f"target mapping for {name!r} contains an invalid path")
            target = safe_relative_path(workspace, relative, must_exist=True)
            if not target.is_file():
                raise ObservationError(f"target mapping must name an existing file: {relative}")
            normalized = target.relative_to(workspace).as_posix()
            if normalized not in result[name]:
                result[name].append(normalized)
    return result


def mapped_targets(names, target_map, workspace, flags):
    targets = []
    for name in names:
        mapped = target_map.get(name)
        if mapped is None and ("/" in name or "\\" in name):
            try:
                path = safe_relative_path(workspace, name, must_exist=True)
                if path.is_file():
                    mapped = [path.relative_to(workspace).as_posix()]
            except (ObservationError, OSError, ValueError):
                pass
        if mapped is None:
            flags.append(f"unmapped legacy target: {name}")
        else:
            targets.extend(path for path in mapped if path not in targets)
    return targets


def string_list(value, field, flags):
    if value is None:
        return []
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return list(value)
    flags.append(f"{field}-invalid")
    return []


def remap_qualifiers(qualifiers, target_map, flags):
    if not isinstance(qualifiers, dict):
        return qualifiers
    result = {}
    for name, value in qualifiers.items():
        for target in target_map.get(name, [name]):
            if target in result and result[target] != value:
                result[target] = [result[target], value]
                flags.append(f"multiple legacy qualifiers for target: {target}")
            else:
                result[target] = copy.deepcopy(value)
    return result


def convert_record(metadata, body, source, source_format, workspace, target_map,
                   source_entry=None, source_preamble=""):
    data, original, flags = copy.deepcopy(metadata), copy.deepcopy(metadata), []
    identifier = data.get("id")
    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 1:
        raise ObservationError(f"{source}: id must be a positive integer")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ObservationError(f"{source}: observation {identifier} needs a nonempty title")
    if "schema_version" in data and data["schema_version"] != SCHEMA_VERSION:
        raise ObservationError(f"{source}: unsupported schema_version {data['schema_version']!r}")
    if source_format == "legacy-monolithic":
        parsed = parse_status(data.get("status"), flags)
        for key, value in parsed.items():
            if key == "status" or key not in data:
                data[key] = value
            elif data[key] != value:
                flags.append(f"conflicting-{key}-metadata")
        if data.get("resolved"):
            flags = [flag for flag in flags if flag != "resolved-date-missing"]
    elif isinstance(data.get("status"), str):
        data["status"] = data["status"].lower()
    legacy = data.pop("skill", None)
    names, candidates, parsed_qualifiers = parse_legacy_targets(legacy, flags)
    if legacy is not None:
        data["legacy_targets"] = copy.deepcopy(legacy if isinstance(legacy, list) else [legacy])
    targets = string_list(data.get("targets"), "targets", flags)
    targets.extend(path for path in mapped_targets(names, target_map, workspace, flags)
                   if path not in targets)
    data["targets"] = targets
    proposed = string_list(data.get("proposed_workflows"), "proposed-workflows", flags)
    for name in string_list(data.pop("proposes_skill", None), "legacy-proposed-workflows", flags) + candidates:
        if name not in proposed:
            proposed.append(name)
    data["proposed_workflows"] = proposed
    old_qualifiers = data.pop("skill_qualifiers", parsed_qualifiers or None)
    if old_qualifiers is not None:
        old_qualifiers = remap_qualifiers(old_qualifiers, target_map, flags)
        if "target_qualifiers" not in data:
            data["target_qualifiers"] = old_qualifiers
        elif data["target_qualifiers"] != old_qualifiers:
            flags.append("conflicting-target-qualifiers; both preserved in migration provenance")
    siblings = data.pop("siblings_checked", None)
    if "related_targets_checked" not in data and siblings is not None:
        data["related_targets_checked"] = siblings
    elif siblings is not None and data.get("related_targets_checked") != siblings:
        flags.append("conflicting-related-targets-check; both preserved in migration provenance")
    if not isinstance(data.get("related_targets_checked"), str) or not data["related_targets_checked"].strip():
        data["related_targets_checked"] = "Not recorded in usable legacy metadata; review required."
        flags.append("related-targets-check-missing-or-invalid")
    data["schema_version"] = SCHEMA_VERSION
    provenance = {"source": str(source), "format": source_format, "original_metadata": original}
    if source_entry is not None:
        provenance["source_entry"] = source_entry
    if source_preamble:
        provenance["source_preamble"] = source_preamble
    data["migration_provenance"] = provenance
    flags.extend(validate_record(data, body, workspace=workspace))
    flags = list(dict.fromkeys(flags))
    if flags:
        previous = data.get("migration_note")
        data["migration_note"] = (
            (str(previous) + "; " if previous else "") + "needs review: " + "; ".join(flags)
        )
    return {"metadata": data, "body": body, "flags": flags}


def source_archive(path, selected_directory, workspace):
    if selected_directory is not None:
        root = (
            selected_directory if selected_directory.name.lower() == "archive"
            else selected_directory / "archive"
        )
        return root if path.is_relative_to(root) else None
    if path.parent != workspace and path.parent.name.lower() == "archive":
        return path.parent
    # Individual nested files need a recognizable log boundary, not an
    # arbitrary ancestor named "archive" outside the owning workspace.
    for parent in path.parents:
        if parent == workspace:
            break
        if parent.name.lower() == "observation-log":
            root = parent / "archive"
            return root if path.is_relative_to(root) else None
    return None


def read_text(path):
    return path.read_text(encoding="utf-8-sig")


def directory_items(path):
    def fail(error):
        raise error

    for root, directories, files in os.walk(path, onerror=fail, followlinks=False):
        directories.sort()
        for name in sorted(directories + files):
            yield Path(root) / name


def collect_inputs(paths, workspace):
    files, floors, directories, ancillary, seen = [], [], [], [], set()
    for raw in paths:
        path = Path(raw).resolve(strict=True)
        if path.is_dir():
            directories.append(path)
            found = []
            for item in directory_items(path):
                if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
                    raise ObservationError(f"directory inputs must not contain symbolic links: {item}")
                if not item.is_file():
                    continue
                if item.name in ANCILLARY_FILES:
                    ancillary.append(item)
                elif item.name == ".id-floor":
                    floors.append(item)
                elif item.suffix.lower() == ".md":
                    found.append(item)
                    files.append((item, True, source_archive(item, path, workspace)))
                else:
                    raise ObservationError(f"unrecognised file in input directory: {item}")
            if not found:
                raise ObservationError(f"no observations found in input directory: {path}")
        elif path.is_file():
            archive = source_archive(path, None, workspace)
            files.append((path, False, archive))
            for floor in (path.parent / ".id-floor", path.parent / "archive"):
                if floor.exists():
                    floors.append(floor)
            if archive is not None:
                floors.append(archive)
        else:
            raise ObservationError(f"input is not a regular file or directory: {path}")
    for path, _, _ in files:
        if path in seen:
            raise ObservationError(f"duplicate input file: {path}")
        seen.add(path)
    return files, floors, directories, ancillary


def id_floor_from(paths):
    maximum = 0
    for raw in paths:
        path = Path(raw).resolve(strict=True)
        candidates = directory_items(path) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
                raise ObservationError(f"ID-floor sources must not contain symbolic links: {candidate}")
            if not candidate.is_file():
                continue
            if candidate.name == ".id-floor":
                text = read_text(candidate).strip()
                if not re.fullmatch(r"\d+", text):
                    raise ObservationError(f"invalid ID floor: {candidate}")
                maximum = max(maximum, int(text))
            elif candidate.suffix.lower() == ".md":
                text = read_text(candidate)
                if FRONTMATTER_RE.match(text):
                    metadata, _ = parse_record(text)
                    identifier = metadata.get("id")
                    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 1:
                        raise ObservationError(f"invalid observation ID in ID-floor source: {candidate}")
                    maximum = max(maximum, identifier)
                else:
                    lines = text.splitlines(keepends=True)
                    for start in entry_starts(lines):
                        maximum = max(maximum, int(ENTRY_RE.match(lines[start].rstrip("\r\n")).group(1)))
                prefix = re.match(r"^(\d+)-", candidate.name)
                if prefix:
                    maximum = max(maximum, int(prefix.group(1)))
    return maximum


def preflight(logs, workspace, target_map, floor_paths):
    files, floor_files, directories, ancillary = collect_inputs(logs, workspace)
    records, identifiers, filenames = [], {}, set()
    for path, directory_input, source_archive_root in files:
        text = read_text(path)
        archive = Path("archive") if source_archive_root is not None else Path()
        if FRONTMATTER_RE.match(text):
            metadata, body = parse_record(text)
            parsed = [
                convert_record(metadata, body, path, "legacy-frontmatter", workspace,
                               target_map, source_entry=text)
            ]
        else:
            if directory_input or archive != Path():
                raise ObservationError(
                    f"{path}: directory/archive monolithic inputs are unsupported; "
                    "pass an active monolithic log as a file, and use --id-floor-from "
                    "for an archive monolith while retaining its source separately"
                )
            parsed = [
                convert_record(entry["metadata"], entry["body"], path, "legacy-monolithic",
                               workspace, target_map, entry["source_entry"], entry["source_preamble"])
                for entry in parse_entries(text, path)
            ]
            if not parsed:
                raise ObservationError(f"no observations found in input: {path}")
        for record in parsed:
            data = record["metadata"]
            if source_archive_root is not None:
                data["migration_provenance"]["source_archive"] = str(source_archive_root)
            identifier = data["id"]
            if identifier in identifiers:
                raise ObservationError(
                    f"duplicate observation ID {identifier}: {identifiers[identifier]} and {path}; "
                    "reconcile IDs before conversion"
                )
            identifiers[identifier] = path
            relative = archive / f"{identifier:04d}-{slugify(data['title'])}.md"
            if relative.as_posix().casefold() in filenames:
                raise ObservationError(f"duplicate output filename: {relative}")
            filenames.add(relative.as_posix().casefold())
            record["relative"] = relative
            record["text"] = dump_record(data, record["body"])
            # Serialization failure is a preflight error, never a partial publish.
            parse_record(record["text"])
            records.append(record)
    if not records:
        raise ObservationError("no observations found; no output created")
    floor = max(max(identifiers), id_floor_from([*floor_files, *floor_paths]))
    directories.extend(Path(path).resolve() for path in [*floor_files, *floor_paths]
                       if Path(path).is_dir())
    return records, floor, directories, ancillary


def remove_owned_output(files, directories):
    """Rollback our unchanged files only; never recursively delete a destination."""
    failures = []
    for path, identity in reversed(files):
        try:
            stat = path.lstat()
            if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) == identity:
                path.unlink()
            else:
                failures.append(f"{path}: changed since publication; retained for reconciliation")
        except FileNotFoundError:
            continue
        except OSError as error:
            failures.append(f"{path}: could not remove owned output: {error}")
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except FileNotFoundError:
            continue
        except OSError as error:
            failures.append(f"{path}: could not remove owned directory: {error}")
    return failures


def publish(records, floor, output):
    if os.path.lexists(output):
        raise ObservationError(f"destination already exists: {output}; use a new --out directory")
    missing_parents, created_parents = [], []
    cursor = output.parent
    while not cursor.exists():
        missing_parents.append(cursor)
        cursor = cursor.parent
    staging = output.parent / f".{output.name}.migrate-{uuid.uuid4().hex}"
    staged = False
    owned_files, owned_directories = [], []
    primary_error, cleanup_failures = None, []
    try:
        for parent in reversed(missing_parents):
            parent.mkdir()
            created_parents.append(parent)
        staging.mkdir()
        staged = True
        contents = [(record["relative"], record["text"]) for record in records]
        contents.append((Path("archive") / ".id-floor", f"{floor}\n"))
        for relative, text in contents:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            exclusive_write(target, text)
        # mkdir reserves the destination exclusively on every supported platform.
        # Subsequent exclusive writes also refuse files introduced by another writer.
        try:
            output.mkdir()
        except FileExistsError as error:
            raise ObservationError(
                f"destination already exists: {output}; use a new --out directory"
            ) from error
        owned_directories.append(output)
        for relative, _ in contents:
            destination = output / relative
            parents = []
            cursor = destination.parent
            while cursor != output:
                parents.append(cursor)
                cursor = cursor.parent
            for parent in reversed(parents):
                if parent not in owned_directories:
                    parent.mkdir()
                    owned_directories.append(parent)
            exclusive_write(destination, read_text(staging / relative))
            stat = destination.stat()
            owned_files.append(
                (destination, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
            )
    except BaseException as error:
        primary_error = error
        cleanup_failures.extend(remove_owned_output(owned_files, owned_directories))
        raise
    finally:
        if staged:
            try:
                shutil.rmtree(staging)
            except FileNotFoundError as error:
                if os.path.lexists(staging):
                    cleanup_failures.append(f"{staging}: incomplete staging cleanup: {error}")
            except OSError as error:
                cleanup_failures.append(f"{staging}: could not remove staging directory: {error}")
        if primary_error is not None:
            cleanup_failures.extend(remove_owned_output([], created_parents))
        if cleanup_failures:
            detail = "cleanup incomplete; inspect retained paths:\n  " + "\n  ".join(cleanup_failures)
            if primary_error is not None:
                print(f"migration cleanup warning: {detail}", file=sys.stderr)
            else:
                raise ObservationError(f"conversion output published, but {detail}")


def report(records, floor, ancillary):
    print(f"parsed {len(records)} observation(s); ID floor: {floor}")
    flagged = [record for record in records if record["metadata"].get("migration_note")]
    print(f"needs human review: {len(flagged)}/{len(records)}")
    for record in flagged:
        print(f"  #{record['metadata']['id']}: {record['metadata']['migration_note']}")
    for path in ancillary:
        print(f"not imported: {path}; preserve principles/review state separately")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, AttributeError):
                pass
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="preflight and report; write nothing")
    mode.add_argument("--convert", action="store_true", help="convert into a new observation-log directory")
    parser.add_argument("logs", nargs="+", help="legacy log files or per-file observation-log directories")
    parser.add_argument("--out", help="new output directory; required for --convert")
    parser.add_argument("--workspace", default=".", help="workspace for target paths (default: current directory)")
    parser.add_argument(
        "--target-map", metavar="JSON_OR_FILE",
        help="JSON object or JSON file mapping historical names to existing target file paths",
    )
    parser.add_argument("--id-floor-from", action="append", default=[], metavar="PATH")
    args = parser.parse_args(argv)
    if args.convert and not args.out:
        parser.error("--convert requires --out naming a new directory")
    try:
        workspace = Path(args.workspace).resolve(strict=True)
        if not workspace.is_dir():
            raise ObservationError(f"workspace is not a directory: {workspace}")
        output = Path(args.out).absolute() if args.convert else None
        if output is not None and os.path.lexists(output):
            raise ObservationError(f"destination already exists: {output}; use a new --out directory")
        target_map = load_target_map(args.target_map, workspace)
        records, floor, directories, ancillary = preflight(
            args.logs, workspace, target_map, args.id_floor_from
        )
        if output is not None:
            resolved_output = output.resolve()
            for directory in directories:
                if resolved_output == directory or directory in resolved_output.parents:
                    raise ObservationError("output must not be inside a source input directory")
        report(records, floor, ancillary)
        if args.convert:
            publish(records, floor, output)
            print(f"wrote {len(records)} observation(s) to {output}; sources unchanged")
        return 0
    except (ObservationError, OSError, UnicodeError, ValueError) as error:
        print(f"migration failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
