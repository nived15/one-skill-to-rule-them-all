"""Initialize, inspect, record, and archive workspace-local observations."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

from observer_common import (
    ObservationError, RESOLVED, STORE_REL, atomic_write, dump_record,
    exclusive_write, iso_date, read_header, read_record, resolve_workspace,
    safe_relative_path, validate_record,
)


def store_path(workspace: Path) -> Path:
    target = safe_relative_path(workspace, STORE_REL.as_posix(), must_exist=False)
    if target != workspace / STORE_REL:
        raise ObservationError("Linked observation storage is not allowed")
    return target


@contextmanager
def store_lock(store: Path):
    lock = store / ".observer.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ObservationError(
            f"Observer store is locked: {lock}. Check for an active writer; "
            "remove a stale lock only after confirming its owner stopped."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock.unlink()


def entry_paths(store: Path, include_archive: bool = False) -> list[Path]:
    log = store / "observation-log"
    folders = [log, log / "archive"] if include_archive else [log]
    paths = []
    for folder in folders:
        if not folder.is_dir() or folder.resolve() != folder.absolute():
            raise ObservationError(f"Missing or linked log directory: {folder}; run init or reconcile migration")
        for path in sorted(folder.iterdir()):
            if path.is_symlink() or path.resolve() != path.absolute():
                raise ObservationError(f"Linked observation entry is not allowed: {path}")
            if path.suffix.lower() == ".md":
                if not path.is_file():
                    raise ObservationError(f"Observation is not a file: {path}")
                paths.append(path)
            elif path.is_dir() and path != log / "archive":
                raise ObservationError(f"Unexpected log subdirectory: {path}")
    return paths


def id_floor(store: Path) -> int:
    floor_path = store / "observation-log" / "archive" / ".id-floor"
    if floor_path.is_symlink():
        raise ObservationError(f"Linked ID floor is not allowed: {floor_path}")
    if not floor_path.is_file():
        raise ObservationError(f"Missing ID floor: {floor_path}; run init")
    value = floor_path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"\d+", value):
        raise ObservationError(f"Invalid ID floor: {floor_path}")
    return int(value)


def highest_id(store: Path) -> int:
    identifiers = {}
    for path in entry_paths(store, include_archive=True):
        header = read_header(path)
        identifier = header.get("id")
        match = re.match(r"^(\d{4,})-", path.name)
        if type(identifier) is not int or identifier < 1 or not match or int(match[1]) != identifier:
            raise ObservationError(f"Invalid ID or filename: {path}")
        if identifier in identifiers:
            raise ObservationError(f"Duplicate id {identifier}: {identifiers[identifier]} and {path}")
        identifiers[identifier] = path
    return max([id_floor(store), *identifiers])


def initialize(workspace: Path) -> Path:
    store = store_path(workspace)
    for legacy in (workspace / "skill-observations" / "log.md",
                   workspace / "skill-observations" / "observation-log",
                   store / "log.md"):
        if legacy.exists():
            raise ObservationError(f"Legacy store detected: {legacy}; reconcile it before initializing another store")
    store.mkdir(parents=True, exist_ok=True)
    with store_lock(store):
        for relative in ("observation-log", "observation-log/archive"):
            target = store / relative
            if target.is_symlink() or target.resolve() != target.absolute():
                raise ObservationError(f"Linked storage directory is not allowed: {target}")
            target.mkdir(exist_ok=True)
        floor = store / "observation-log" / "archive" / ".id-floor"
        if not floor.exists():
            existing_ids = []
            for path in entry_paths(store, include_archive=True):
                header = read_header(path)
                identifier = header.get("id")
                if type(identifier) is not int or identifier < 1:
                    raise ObservationError(f"Cannot initialize ID floor from invalid record: {path}")
                existing_ids.append(identifier)
            exclusive_write(floor, f"{max(existing_ids, default=0)}\n")
        highest_id(store)
        principles = store / "cross-cutting-principles.md"
        marker = store / "last-review-date.txt"
        ignore = store / ".gitignore"
        for path in (principles, marker, ignore):
            if path.is_symlink():
                raise ObservationError(f"Linked state file is not allowed: {path}")
        if not ignore.exists():
            exclusive_write(ignore, "*\n!.gitignore\n!README.md\n")
        if not principles.exists():
            exclusive_write(principles, "# Cross-cutting principles\n\nNo approved principles yet.\n")
        if not marker.exists():
            exclusive_write(marker, "never\n")
        value = marker.read_text(encoding="utf-8").strip()
        if value != "never" and iso_date(value) is None:
            raise ObservationError("last-review-date.txt must contain 'never' or YYYY-MM-DD")
    return store


def scan(workspace: Path) -> dict:
    store = store_path(workspace)
    records = []
    errors = []
    with store_lock(store):
        for path in entry_paths(store):
            try:
                data = read_header(path)
            except (ObservationError, OSError) as exc:
                errors.append(f"{path.name}: {exc}")
                records.append({"file": path.name, "status": "review-required"})
                continue
            status = data.get("status")
            if not isinstance(status, str) or status not in RESOLVED | {"open", "parked"}:
                errors.append(f"{path.name}: invalid or missing status; requires review")
                status = "review-required"
            if data.get("migration_note"):
                errors.append(f"{path.name}: {data['migration_note']}")
            if status == "parked" and not data.get("parked_until"):
                errors.append(f"{path.name}: parked_until is missing; requires review")
                status = "review-required"
            header_errors = [
                error for error in validate_record(data, "", workspace, path.name)
                if not error.startswith("body requires ")
            ]
            if header_errors:
                errors.extend(f"{path.name}: {error}" for error in header_errors)
                status = "review-required"
            target_summary = data.get("targets", [])
            workflow_summary = data.get("proposed_workflows", [])
            records.append({
                "file": path.name,
                "id": data.get("id") if type(data.get("id")) is int else None,
                "title": data.get("title") if isinstance(data.get("title"), str) else None,
                "status": status,
                "targets": target_summary if isinstance(target_summary, list) and
                all(isinstance(item, str) for item in target_summary) else [],
                "proposed_workflows": workflow_summary if isinstance(workflow_summary, list) and
                all(isinstance(item, str) for item in workflow_summary) else [],
                "parked_until": data.get("parked_until") if isinstance(data.get("parked_until"), str) else None,
            })
        try:
            highest_id(store)
        except ObservationError as exc:
            errors.append(str(exc))
        marker = store / "last-review-date.txt"
        if marker.is_symlink():
            raise ObservationError("Linked review marker is not allowed")
        principles = store / "cross-cutting-principles.md"
        if not principles.is_file() or principles.is_symlink():
            raise ObservationError("Missing or linked cross-cutting-principles.md; run init or reconcile state")
        reviewed = marker.read_text(encoding="utf-8").strip()
        date = iso_date(reviewed)
        if reviewed != "never" and date is None:
            raise ObservationError("Invalid last-review-date.txt")
    opened = sum(record["status"] in ("open", "review-required") for record in records)
    return {
        "records": records, "count": len(records), "open_count": opened,
        "last_review": reviewed,
        "review_due": bool(opened and (date is None or (dt.date.today() - date).days >= 7)),
        "errors": errors,
    }


def archive_locked(workspace: Path, store: Path, today: dt.date) -> list[str]:
    eligible = []
    for path in entry_paths(store):
        data, body = read_record(path)
        errors = validate_record(data, body, workspace, path.name)
        if errors:
            raise ObservationError(f"{path.name}: {'; '.join(errors)}")
        if data["status"] in RESOLVED and iso_date(data["resolved"]) < today:
            target = path.parent / "archive" / path.name
            if target.exists():
                raise ObservationError(f"Archive collision: {target}")
            eligible.append((path, target))
    moved = []
    for source, target in eligible:
        # Hard-link then unlink gives a no-clobber move on both Windows and POSIX.
        os.link(source, target)
        source.unlink()
        moved.append(target.name)
    return moved


def archive(workspace: Path) -> list[str]:
    store = store_path(workspace)
    with store_lock(store):
        highest = highest_id(store)
        atomic_write(store / "observation-log" / "archive" / ".id-floor", f"{highest}\n")
        return archive_locked(workspace, store, dt.date.today())


def record(workspace: Path, draft: Path) -> Path:
    data, body = read_record(draft)
    if data.get("status") != "open":
        raise ObservationError("New observations must have status: open")
    if data.get("migration_note"):
        raise ObservationError("Resolve migration warnings before recording a new observation")
    store = store_path(workspace)
    with store_lock(store):
        identifier = highest_id(store) + 1
        data["id"] = identifier
        errors = validate_record(data, body, workspace)
        if errors:
            raise ObservationError("; ".join(errors))
        slug = re.sub(r"[^a-z0-9]+", "-", data["title"].lower()).strip("-")[:60].rstrip("-") or "observation"
        output = store / "observation-log" / f"{identifier:04d}-{slug}.md"
        archive_locked(workspace, store, dt.date.today())
        # Reserve the number first. Gaps after failed writes are safer than ID reuse.
        atomic_write(store / "observation-log" / "archive" / ".id-floor", f"{identifier}\n")
        exclusive_write(output, dump_record(data, body))
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Explicit repository or folder root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("scan")
    commands.add_parser("archive")
    add = commands.add_parser("record")
    add.add_argument("--input", required=True, type=Path, help="Observation Markdown draft; id is assigned")
    args = parser.parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        if args.command == "init":
            print(f"Initialized: {initialize(workspace)}")
        elif args.command == "record":
            print(f"Recorded: {record(workspace, args.input)}")
        elif args.command == "archive":
            print(json.dumps({"archived": archive(workspace)}))
        else:
            result = scan(workspace)
            print(json.dumps(result, indent=2, default=str))
            return 1 if result["errors"] else 0
    except (ObservationError, OSError) as exc:
        print(f"Observer error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
