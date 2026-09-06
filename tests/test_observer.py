from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / ".github" / "skills" / "task-observer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import observer
from observer_common import (
    ObservationError, STORE_REL, dump_record, parse_record, read_header, read_record,
    safe_relative_path, validate_record,
)

spec = importlib.util.spec_from_file_location("observer_validator", SCRIPTS / "validate-copilot-observer.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

BODY = "\n**Issue:** The user corrected a repeated assumption.\n\n**Suggested improvement:** Read the convention.\n\n**Principle:** Consult actual project evidence.\n"


def metadata(**updates):
    result = {
        "schema_version": 1, "id": 1, "title": "Use existing conventions",
        "status": "open", "type": "open-source",
        "targets": [".github/copilot-instructions.md"], "proposed_workflows": [],
        "related_targets_checked": "none", "area": "Development",
        "date": "2026-01-01", "session_context": "An explicit user correction.",
        "parked_until": None, "resolved": None, "resolution": None, "reference": None,
    }
    result.update(updates)
    return result


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="observer workspace ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / ".github").mkdir()
        (self.root / ".github" / "copilot-instructions.md").write_text("# Instructions\n", encoding="utf-8")
        self.store = observer.initialize(self.root)

    def draft(self, **updates):
        path = self.store / "draft.md"
        path.write_text(dump_record(metadata(**updates), BODY), encoding="utf-8")
        return path

    def test_initialize_preserves_user_state_and_never(self):
        principles = self.store / "cross-cutting-principles.md"
        marker = self.store / "last-review-date.txt"
        self.assertEqual(marker.read_text().strip(), "never")
        principles.write_text("# Approved principles\n", encoding="utf-8")
        marker.write_text("2026-01-02\n", encoding="utf-8")
        observer.initialize(self.root)
        self.assertEqual(principles.read_text(), "# Approved principles\n")
        self.assertEqual(marker.read_text(), "2026-01-02\n")
        self.assertIn("*\n", (self.store / ".gitignore").read_text())

    def test_fresh_scan_is_honestly_empty(self):
        result = observer.scan(self.root)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["review_due"])

    def test_assigns_ids_and_scans_real_headers(self):
        first = observer.record(self.root, self.draft(id=0))
        second = observer.record(self.root, self.draft(id=0))
        self.assertEqual(read_record(first)[0]["id"], 1)
        self.assertEqual(read_record(second)[0]["id"], 2)
        result = observer.scan(self.root)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["open_count"], 2)
        self.assertTrue(result["review_due"])

    def test_draft_failure_does_not_issue_id(self):
        with self.assertRaisesRegex(ObservationError, "session_context"):
            observer.record(self.root, self.draft(session_context=""))
        self.assertEqual(observer.id_floor(self.store), 0)
        self.assertEqual(observer.entry_paths(self.store), [])

    def test_rejects_non_open_draft(self):
        with self.assertRaisesRegex(ObservationError, "status: open"):
            observer.record(self.root, self.draft(status="parked", parked_until="Dependency lands"))

    def test_local_lock_refuses_second_writer(self):
        with observer.store_lock(self.store):
            with self.assertRaisesRegex(ObservationError, "locked"):
                observer.record(self.root, self.draft())
        self.assertFalse((self.store / ".observer.lock").exists())

    def test_archive_grace_parked_and_floor(self):
        today = dt.date.today()
        previous = observer.record(self.root, self.draft())
        current = observer.record(self.root, self.draft())
        parked = observer.record(self.root, self.draft())
        for path, date in ((previous, today - dt.timedelta(days=1)), (current, today)):
            data, body = read_record(path)
            data.update(status="actioned", resolved=date.isoformat(), resolution="Approved and applied.")
            path.write_text(dump_record(data, body), encoding="utf-8")
        data, body = read_record(parked)
        data.update(status="parked", parked_until="The supported API becomes available.")
        parked.write_text(dump_record(data, body), encoding="utf-8")
        moved = observer.archive(self.root)
        self.assertEqual(moved, [previous.name])
        self.assertTrue(current.exists())
        self.assertTrue(parked.exists())
        self.assertEqual(observer.id_floor(self.store), 3)
        fourth = observer.record(self.root, self.draft())
        self.assertEqual(read_record(fourth)[0]["id"], 4)

    def test_duplicate_ids_never_silently_collapse(self):
        first = observer.record(self.root, self.draft())
        duplicate = first.with_name("0001-another-title.md")
        duplicate.write_text(first.read_text(), encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "Duplicate id"):
            observer.record(self.root, self.draft())
        self.assertTrue(first.exists())
        self.assertTrue(duplicate.exists())

    def test_unknown_status_reported_not_dropped(self):
        path = observer.record(self.root, self.draft())
        data, body = read_record(path)
        data.pop("status")
        path.write_text(dump_record(data, body), encoding="utf-8")
        result = observer.scan(self.root)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["open_count"], 1)
        self.assertTrue(result["errors"])

    def test_malformed_headers_are_enumerated_in_scan(self):
        path = self.store / "observation-log" / "0001-broken.md"
        path.write_text("# no frontmatter\n", encoding="utf-8")
        result = observer.scan(self.root)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["open_count"], 1)
        self.assertEqual(result["records"][0]["status"], "review-required")
        self.assertTrue(result["errors"])

    def test_legacy_schema_is_flagged_during_header_scan(self):
        path = observer.record(self.root, self.draft())
        data, body = read_record(path)
        data["skill"] = data.pop("targets")
        data.pop("schema_version")
        path.write_text(dump_record(data, body), encoding="utf-8")
        result = observer.scan(self.root)
        self.assertEqual(result["open_count"], 1)
        self.assertTrue(any("schema_version" in error for error in result["errors"]))

    def test_resolved_target_can_be_retired_before_archival(self):
        path = observer.record(self.root, self.draft())
        data, body = read_record(path)
        data.update(status="actioned", resolved="2026-01-02", resolution="Approved target retirement.")
        path.write_text(dump_record(data, body), encoding="utf-8")
        (self.root / ".github" / "copilot-instructions.md").unlink()
        self.assertEqual(observer.archive(self.root), [path.name])

    def test_invalid_floor_and_disappeared_store_fail(self):
        floor = self.store / "observation-log" / "archive" / ".id-floor"
        floor.write_text("not-an-id", encoding="ascii")
        with self.assertRaisesRegex(ObservationError, "Invalid ID floor"):
            observer.record(self.root, self.draft())
        floor.unlink()
        with self.assertRaisesRegex(ObservationError, "Missing ID floor"):
            observer.record(self.root, self.draft())

    def test_legacy_store_blocks_second_store(self):
        legacy = self.root / "skill-observations"
        legacy.mkdir()
        (legacy / "log.md").write_text("# Legacy log", encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "Legacy store"):
            observer.initialize(self.root)

    def test_explicit_workspace_from_different_cwd(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "observer.py"), "--workspace", str(self.root), "scan"],
            cwd=self.root / ".github", text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["count"], 0)
        self.assertFalse((self.root / ".github" / STORE_REL).exists())

    def test_worktree_marker_is_not_followed(self):
        (self.root / ".git").write_text("gitdir: unavailable-main-checkout\n", encoding="utf-8")
        self.assertEqual(observer.initialize(self.root), self.store)

    def test_archive_refuses_colliding_record_without_changing_either(self):
        path = observer.record(self.root, self.draft())
        data, body = read_record(path)
        data.update(status="actioned", resolved="2026-01-02", resolution="Approved.")
        text = dump_record(data, body)
        path.write_text(text, encoding="utf-8")
        destination = path.parent / "archive" / path.name
        destination.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "Duplicate id"):
            observer.archive(self.root)
        self.assertEqual(path.read_text(), text)
        self.assertEqual(destination.read_text(), text)

    def test_record_uses_floor_even_when_log_empty(self):
        floor = self.store / "observation-log" / "archive" / ".id-floor"
        floor.write_text("109\n", encoding="ascii")
        path = observer.record(self.root, self.draft())
        self.assertTrue(path.name.startswith("0110-"))

    def test_record_does_not_overwrite_existing_path(self):
        from unittest.mock import patch
        path = self.store / "observation-log" / "0001-use-existing-conventions.md"
        path.write_text(dump_record(metadata(), BODY), encoding="utf-8")
        original = path.read_bytes()
        with patch.object(observer, "highest_id", return_value=0):
            with self.assertRaises(FileExistsError):
                observer.record(self.root, self.draft())
        self.assertEqual(path.read_bytes(), original)


class SchemaTests(unittest.TestCase):
    def test_roundtrip_preserves_unicode_body_and_metadata(self):
        data, body = parse_record(dump_record(metadata(title="A Unicode \u2192 title"), BODY + "\nEvidence: \u00e9.\n"))
        self.assertEqual(data["title"], "A Unicode \u2192 title")
        self.assertEqual(body, BODY + "\nEvidence: \u00e9.\n")
        self.assertEqual(validate_record(data, body), [])

    def test_duplicate_yaml_key_fails(self):
        with self.assertRaisesRegex(ObservationError, "Duplicate YAML key"):
            parse_record("---\nid: 1\nid: 2\n---\n")

    def test_header_scan_respects_indented_block_scalars(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.md"
            path.write_text(
                "---\nrelated_targets_checked: |\n  Related files\n  ---\n  Checked them\n"
                "status: open\n---\nBody must not enter the header.\n", encoding="utf-8",
            )
            self.assertEqual(read_header(path)["status"], "open")
            self.assertIn("---", read_header(path)["related_targets_checked"])

    def test_malformed_and_non_mapping_frontmatter(self):
        for text in ("# no header", "---\nid: [\n---\n", "---\n- not-a-mapping\n---\n",
                     "---\ndate: 2026-02-30\n---\n"):
            with self.subTest(text=text), self.assertRaises(ObservationError):
                parse_record(text)

    def test_invalid_schema_cases(self):
        cases = (
            {"id": True}, {"schema_version": True}, {"date": "2026-02-30"},
            {"targets": "not-a-list"}, {"related_targets_checked": ""},
            {"status": ["open"]}, {"status": "parked", "parked_until": ""},
            {"status": "actioned"}, {"targets": ["../private.md"]},
            {"reference": "C:/private/evidence.md"},
            {"resolved": "2026-01-02"},
            {"sanitized": "true"}, {"shared_for_review": 1},
            {"target_qualifiers": ["not-a-map"]},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                self.assertTrue(validate_record(metadata(**updates), BODY))

    def test_all_resolved_states_and_parked(self):
        for state in ("actioned", "declined", "superseded"):
            self.assertEqual(validate_record(metadata(status=state, resolved="2026-01-02", resolution="Approved decision."), BODY), [])
        self.assertEqual(validate_record(metadata(status="parked", parked_until="Dependency enabled"), BODY), [])

    def test_missing_body_evidence_rejected(self):
        self.assertTrue(validate_record(metadata(), "**Issue:** \n\n**Principle:** Only a principle.\n"))

    def test_reference_and_target_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for target in ("../escape.md", "/absolute.md", "C:/escape.md", "C:relative.md", "a\\b.md"):
                with self.subTest(target=target), self.assertRaises(ObservationError):
                    safe_relative_path(root, target, must_exist=False)

    def test_bootstrap_local_link_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            doc = root / "README.md"
            doc.write_text("[missing](missing.md)\n[external](https://example.com)\n", encoding="utf-8")
            self.assertEqual(len(validator.validate_links(doc, root)), 1)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="copilot adoption ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.skill = self.root / ".github" / "skills" / "task-observer"
        (self.skill / "references").mkdir(parents=True)
        (self.skill / "scripts").mkdir()
        prompts = self.root / ".github" / "prompts"
        prompts.mkdir()
        (self.skill / "SKILL.md").write_text(
            "---\nname: task-observer\ndescription: Observe corrections.\n---\n# Task Observer\n",
            encoding="utf-8",
        )
        (self.skill / "requirements.txt").write_text("PyYAML>=6.0.2,<7\n", encoding="utf-8")
        for name in validator.REFERENCES:
            (self.skill / "references" / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        for name in ("observer.py", "observer_common.py", "migrate-log.py", "review.py", "validate-copilot-observer.py"):
            (self.skill / "scripts" / name).write_text("# Fixture resource\n", encoding="utf-8")
        for name in validator.PROMPTS:
            (prompts / f"{name}.prompt.md").write_text(
                "---\ndescription: Observe work.\nagent: agent\n---\n"
                "[Task Observer](../skills/task-observer/SKILL.md)\n", encoding="utf-8",
            )
        (self.root / ".github" / "copilot-instructions.md").write_text(
            "[Observer](skills/task-observer/SKILL.md)\n", encoding="utf-8",
        )

    def test_minimal_native_installation_is_valid(self):
        self.assertEqual(validator.validate_workspace(self.root), [])

    def test_root_skill_duplicate_fails(self):
        (self.root / "SKILL.md").write_text("# Duplicate\n", encoding="utf-8")
        self.assertTrue(any("Obsolete root" in error for error in validator.validate_workspace(self.root)))

    def test_missing_colocated_resource_fails(self):
        (self.skill / "scripts" / "observer.py").unlink()
        self.assertTrue(any("observer.py" in error for error in validator.validate_workspace(self.root)))

    def test_wrong_native_name_fails(self):
        (self.skill / "SKILL.md").write_text(
            "---\nname: incorrect-name\ndescription: Observe.\n---\n", encoding="utf-8",
        )
        self.assertTrue(any("Native skill name" in error for error in validator.validate_workspace(self.root)))

    def test_instruction_style_metadata_in_prompt_fails(self):
        path = self.root / ".github" / "prompts" / "observer-start.prompt.md"
        path.write_text(
            "---\ndescription: Observe.\napplyTo: '**'\n---\n"
            "[Observer](../skills/task-observer/SKILL.md)\n", encoding="utf-8",
        )
        self.assertTrue(any("applyTo" in error for error in validator.validate_workspace(self.root)))

    def test_initialized_private_installation_stays_valid(self):
        observer.initialize(self.root)
        self.assertEqual(validator.validate_workspace(self.root), [])

    def test_adopter_can_keep_unrelated_root_scripts_and_references(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "build.py").write_text("# Project build\n", encoding="utf-8")
        (self.root / "references").mkdir()
        (self.root / "references" / "architecture.md").write_text("# Project architecture\n", encoding="utf-8")
        self.assertEqual(validator.validate_workspace(self.root), [])

    def test_complete_skill_adopts_without_source_repository_documents(self):
        source = SCRIPTS.parents[3]
        shutil.rmtree(self.skill)
        shutil.copytree(SCRIPTS.parent, self.skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for prompt in (source / ".github" / "prompts").glob("*.prompt.md"):
            shutil.copyfile(prompt, self.root / ".github" / "prompts" / prompt.name)
        bootstrap = (source / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        (self.root / ".github" / "copilot-instructions.md").write_text(
            bootstrap.split("## Repository conventions", 1)[0], encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(self.skill / "scripts" / "observer.py"),
             "--workspace", str(self.root), "init"],
            cwd=self.root.parent, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "README.md").exists())
        self.assertFalse((self.root / "LICENSE.txt").exists())
        self.assertEqual(validator.validate_workspace(self.root), [])


if __name__ == "__main__":
    unittest.main()
