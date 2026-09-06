"""Migration tests use synthetic, provider-neutral evidence and local fixtures."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "skills" / "task-observer" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("migrate_log", SCRIPTS / "migrate-log.py")
migrate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migrate)

BODY = (
    "\n**Issue:** A repeatable edge case — café.\n\n"
    "**Suggested improvement:** Check the actual workspace.\n\n"
    "**Principle:** Confirm evidence before changing rules.\n"
    "\n**Unknown label:** Keep this literal text and its trailing spaces.  \n"
)
TARGET = ".github/prompts/existing.prompt.md"
SECOND_TARGET = ".github/instructions/additional.instructions.md"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".migration-test-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(self.cleanup_fixture)
        for relative in (TARGET, SECOND_TARGET):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Existing approved guidance.\n", encoding="utf-8")
        self.source = self.root / "legacy"
        self.source.mkdir()
        self.out = self.root / "converted"
        self.mapping = {"old-workflow": TARGET}

    def cleanup_fixture(self):
        for attempt in range(8):
            try:
                shutil.rmtree(self.root)
                return
            except OSError as error:
                if getattr(error, "winerror", None) not in (32, 33) or attempt == 7:
                    raise
                time.sleep(0.05 * 2 ** attempt)

    def metadata(self, identifier=1, **extra):
        result = {
            "id": identifier,
            "title": "Keep the evidence",
            "status": "open",
            "type": "internal",
            "skill": ["old-workflow"],
            "area": "review",
            "date": "2026-08-01",
            "session_context": "Synthetic migration test",
            "siblings_checked": "Checked related files; no propagation.",
        }
        result.update(extra)
        return result

    def write_record(self, path=None, identifier=1, body=BODY, **extra):
        path = path or self.source / f"{identifier:04d}-legacy.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            migrate.dump_record(self.metadata(identifier, **extra), body),
            encoding="utf-8", newline="",
        )
        return path

    def monolith(self, status="OPEN", identifier=1, title="Legacy entry", **extra):
        labels = {
            "Status": status,
            "Date": "2026-08-01",
            "Skill": "old-workflow",
            "Type": "internal",
            "Phase/Area": "review",
            "Session context": "Synthetic migration test",
            "Siblings checked": "Checked related files; no propagation.",
        }
        labels.update(extra)
        return (
            f"### Observation {identifier}: {title}\n"
            + "".join(f"**{key}:** {value}\n" for key, value in labels.items())
            + BODY
        )

    def run_main(self, *arguments, mapping=True):
        args = ["--workspace", str(self.root)]
        if mapping:
            args += ["--target-map", json.dumps(self.mapping)]
        args += [str(arg) for arg in arguments]
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = migrate.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def convert(self, *inputs, mapping=True):
        return self.run_main("--convert", *(inputs or [self.source]), "--out", self.out, mapping=mapping)

    def records(self):
        return {
            data["id"]: (data, body, path)
            for path in self.out.rglob("*.md")
            for data, body in [migrate.parse_record(path.read_text(encoding="utf-8"))]
        }

    def snapshot(self):
        return {
            path.relative_to(self.root).as_posix(): (
                "dir" if path.is_dir() else path.read_bytes()
            )
            for path in self.root.rglob("*")
        }

    def test_per_file_preserves_metadata_qualifiers_and_body(self):
        original = self.metadata(
            proposes_skill=["new-workflow"],
            skill_qualifiers={"old-workflow": "specific section"},
            reference=TARGET,
            migration_provenance={"old_import": "retain prior provenance"},
            custom_metadata={"nested": [1, True, "unknown"]},
        )
        source = self.source / "old.md"
        source.write_text(migrate.dump_record(original, BODY), encoding="utf-8")
        original_bytes = source.read_bytes()
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        data, body, _ = self.records()[1]
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(body, BODY)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["targets"], [TARGET])
        self.assertEqual(data["proposed_workflows"], ["new-workflow"])
        self.assertEqual(data["target_qualifiers"], {TARGET: "specific section"})
        self.assertEqual(data["related_targets_checked"], original["siblings_checked"])
        self.assertEqual(data["legacy_targets"], ["old-workflow"])
        self.assertEqual(data["custom_metadata"], original["custom_metadata"])
        self.assertEqual(data["migration_provenance"]["original_metadata"], original)
        for field in ("skill", "proposes_skill", "siblings_checked", "skill_qualifiers", "migration_note"):
            self.assertNotIn(field, data)
        for field in ("id", "title", "status", "type", "area", "date", "session_context", "reference"):
            self.assertEqual(data[field], original[field])
        self.assertEqual(migrate.validate_record(data, body, workspace=self.root), [])

    def test_all_monolithic_states_and_resolution_dates(self):
        statuses = [
            "OPEN — revisit the note from 2026-08-09",
            "ACTIONED (2026-08-10) — Applied approved edit",
            "DECLINED (2026-08-11) — Not repeatable",
            "SUPERSEDED (2026-08-12) — Replaced by observation 8",
            "PARKED (until the upstream fix ships)",
            "ACTIONED — mentioned in review 2026-08-14",
            "DECLINED (review discussed 2026-08-15)",
        ]
        source = self.root / "log.md"
        preamble = "# Historical observations\n\n## Retained principles\nDo not discard me.\n\n"
        text = preamble + "\n".join(
            self.monolith(status, index) for index, status in enumerate(statuses, 1)
        )
        source.write_text(text, encoding="utf-8")
        original = source.read_bytes()
        code, report, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        records = self.records()
        self.assertEqual([records[i][0]["status"] for i in range(1, 8)],
                         ["open", "actioned", "declined", "superseded", "parked", "actioned", "declined"])
        self.assertEqual(records[2][0]["resolved"], "2026-08-10")
        self.assertEqual(records[2][0]["resolution"], "Applied approved edit")
        self.assertEqual(records[5][0]["parked_until"], "the upstream fix ships")
        self.assertNotIn("resolved", records[5][0])
        self.assertNotIn("resolution", records[5][0])
        self.assertNotIn("resolution", records[1][0])
        self.assertIn("2026-08-09", records[1][0]["status_note"])
        for identifier in (6, 7):
            self.assertNotIn("resolved", records[identifier][0])
            self.assertIn("resolved-date-missing", records[identifier][0]["migration_note"])
            self.assertIn(f"#{identifier}", report)
        self.assertEqual(records[6][0]["resolved_hint"], "2026-08-14")
        self.assertEqual(records[1][0]["migration_provenance"]["source_preamble"], preamble)
        self.assertEqual(source.read_bytes(), original)

    def test_explicit_parked_and_resolution_fields_preserved(self):
        source = self.root / "log.md"
        source.write_text(
            self.monolith("PARKED", 1, **{"Parked until": "upstream confirms compatibility"})
            + self.monolith("ACTIONED", 2, Resolved="2026-08-20", Resolution="Confirmed applied"),
            encoding="utf-8",
        )
        code, _, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        records = self.records()
        self.assertEqual(records[1][0]["parked_until"], "upstream confirms compatibility")
        self.assertEqual(records[2][0]["resolved"], "2026-08-20")
        self.assertEqual(records[2][0]["resolution"], "Confirmed applied")
        self.assertNotIn("migration_note", records[2][0])

    def test_monolithic_qualifiers_references_unknown_labels_and_fences(self):
        source = self.root / "log.md"
        extra_body = (
            "\n```text\n### Observation 999: Not an actual observation\n```\n"
            "\n## A body heading must survive\n---\n"
        )
        text = self.monolith(
            **{"Skill": "old-workflow (specific section)", "Reference files": TARGET}
        ) + extra_body
        source.write_text(text, encoding="utf-8")
        code, _, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        data, body, _ = self.records()[1]
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(data["target_qualifiers"], {TARGET: "specific section"})
        self.assertEqual(data["area"], "review")
        self.assertEqual(data["reference"], TARGET)
        self.assertEqual(body, BODY.lstrip("\n") + extra_body)
        self.assertEqual(data["migration_provenance"]["source_entry"], text)

    def test_candidates_are_not_inferred_targets_from_notes(self):
        source = self.root / "log.md"
        source.write_text(
            self.monolith(**{"Skill": "New skill candidate: candidate (could extend old-workflow)"}),
            encoding="utf-8",
        )
        code, _, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        data = self.records()[1][0]
        self.assertEqual(data["targets"], [])
        self.assertEqual(data["proposed_workflows"], ["candidate"])
        self.assertEqual(data["target_qualifiers"], {"candidate": "could extend old-workflow"})

    def test_missing_mapping_is_explicit_and_raw_names_preserved(self):
        self.write_record(skill=["unmapped", "another-name"], custom_field="Do not execute this note.")
        code, report, errors = self.convert(mapping=False)
        self.assertEqual(code, 0, errors)
        data = self.records()[1][0]
        self.assertEqual(data["targets"], [])
        self.assertEqual(data["legacy_targets"], ["unmapped", "another-name"])
        for name in ("unmapped", "another-name"):
            self.assertIn(f"unmapped legacy target: {name}", data["migration_note"])
            self.assertIn(name, report)
        self.assertEqual(data["custom_field"], "Do not execute this note.")

    def test_split_target_mapping_and_existing_path(self):
        self.write_record(skill=["old-workflow", TARGET], skill_qualifiers={"old-workflow": "section"})
        self.mapping["old-workflow"] = [TARGET, SECOND_TARGET]
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.records()[1][0]["targets"], [TARGET, SECOND_TARGET])
        self.assertEqual(self.records()[1][0]["target_qualifiers"],
                         {TARGET: "section", SECOND_TARGET: "section"})
        self.assertNotIn("migration_note", self.records()[1][0])

    def test_qualifier_collisions_preserve_both_details_and_require_review(self):
        self.write_record(
            skill=["old-workflow", "other-workflow"],
            skill_qualifiers={"old-workflow": "first section", "other-workflow": "second section"},
        )
        self.mapping["other-workflow"] = TARGET
        code, report, errors = self.convert()
        self.assertEqual(code, 0, errors)
        data = self.records()[1][0]
        self.assertEqual(data["target_qualifiers"], {TARGET: ["first section", "second section"]})
        self.assertIn("multiple legacy qualifiers", data["migration_note"])
        self.assertIn("needs human review: 1/1", report)

    def test_bad_mapping_fails_preflight(self):
        self.write_record()
        for mapping in (
            {"old-workflow": "../escape.md"},
            {"old-workflow": ".github/prompts/missing.prompt.md"},
            {"old-workflow": ".github/prompts"},
            {"old-workflow": []},
            {"old-workflow": [TARGET, None]},
        ):
            with self.subTest(mapping=mapping):
                before = self.snapshot()
                self.mapping = mapping
                code, _, _ = self.convert()
                self.assertEqual(code, 1)
                self.assertEqual(self.snapshot(), before)

    def test_duplicate_json_mapping_key_rejected(self):
        self.write_record()
        code, _, errors = self.run_main(
            "--check", self.source, "--target-map",
            '{"old-workflow":"a.md","old-workflow":"b.md"}', mapping=False,
        )
        self.assertEqual(code, 1)
        self.assertIn("duplicate JSON mapping key", errors)

    def test_target_mapping_json_file_is_read_only_and_supports_split_targets(self):
        self.write_record()
        mapping_file = self.root / "mapping with spaces.json"
        mapping_file.write_text(
            json.dumps({"old-workflow": [TARGET, SECOND_TARGET]}), encoding="utf-8"
        )
        original = mapping_file.read_bytes()
        before = self.snapshot()
        code, _, errors = self.run_main(
            "--check", self.source, "--target-map", mapping_file, mapping=False
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.snapshot(), before)
        code, _, errors = self.run_main(
            "--convert", self.source, "--out", self.out,
            "--target-map", mapping_file, mapping=False,
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.records()[1][0]["targets"], [TARGET, SECOND_TARGET])
        self.assertEqual(mapping_file.read_bytes(), original)

    def test_bad_target_mapping_files_fail_without_writes(self):
        self.write_record()
        mapping_file = self.root / "mapping.json"
        for text in ("", "{invalid JSON", '{"same":"a","same":"b"}', "[]"):
            with self.subTest(text=text):
                mapping_file.write_text(text, encoding="utf-8")
                before = self.snapshot()
                code, _, errors = self.run_main(
                    "--convert", self.source, "--out", self.out,
                    "--target-map", mapping_file, mapping=False,
                )
                self.assertEqual(code, 1)
                self.assertIn("--target-map", errors)
                self.assertEqual(self.snapshot(), before)

    def test_duplicate_ids_different_titles_fail_entire_batch(self):
        first = self.write_record(self.source / "first.md", title="First")
        second = self.write_record(self.source / "second.md", title="Different")
        before = self.snapshot()
        code, _, errors = self.convert(first, second)
        self.assertEqual(code, 1)
        self.assertIn("duplicate observation ID", errors)
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_ids_and_names_never_overwrite(self):
        first = self.write_record(self.source / "one" / "same.md")
        second = self.write_record(self.source / "two" / "same.md")
        before = self.snapshot()
        code, _, errors = self.convert(first, second)
        self.assertEqual(code, 1)
        self.assertIn("duplicate observation ID", errors)
        self.assertEqual(self.snapshot(), before)

    def test_same_titles_with_distinct_ids_keep_both(self):
        self.write_record(identifier=1)
        self.write_record(identifier=2)
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        self.assertEqual(len(self.records()), 2)
        self.assertTrue((self.out / "0001-keep-the-evidence.md").exists())
        self.assertTrue((self.out / "0002-keep-the-evidence.md").exists())

    def test_duplicate_monolithic_ids_fail(self):
        source = self.root / "log.md"
        source.write_text(self.monolith(title="First") + self.monolith(title="Different"), encoding="utf-8")
        code, _, errors = self.convert(source)
        self.assertEqual(code, 1)
        self.assertIn("duplicate observation ID", errors)
        self.assertFalse(self.out.exists())

    def test_duplicate_yaml_keys_and_malformed_batch_fail(self):
        first = self.write_record(identifier=1)
        second = self.source / "second.md"
        for text in ("---\nid: 2\nid: 3\n---\nbody\n", "---\nid: [unclosed\n---\n"):
            with self.subTest(text=text):
                second.write_text(text, encoding="utf-8")
                before = self.snapshot()
                code, _, _ = self.convert(first, second)
                self.assertEqual(code, 1)
                self.assertEqual(self.snapshot(), before)

    def test_duplicate_monolithic_metadata_is_rejected(self):
        source = self.root / "log.md"
        source.write_text(
            self.monolith().replace("**Date:**", "**Status:** ACTIONED\n**Date:**"), encoding="utf-8"
        )
        code, _, errors = self.convert(source)
        self.assertEqual(code, 1)
        self.assertIn("duplicate metadata status", errors)

    def test_check_writes_nothing_including_bytecode(self):
        self.write_record()
        isolated = self.root / "isolated-tools"
        isolated.mkdir()
        for name in ("migrate-log.py", "observer_common.py"):
            shutil.copyfile(SCRIPTS / name, isolated / name)
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, str(isolated / "migrate-log.py"), "--check", str(self.source),
             "--out", str(self.root / "absent" / "output"),
             "--target-map", json.dumps(self.mapping)],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((isolated / "__pycache__").exists())

    def test_mode_is_required_conflicting_modes_and_missing_output_rejected(self):
        self.write_record()
        for flags in ([], ["--check", "--convert"], ["--convert"]):
            with self.subTest(flags=flags):
                before = self.snapshot()
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "migrate-log.py"), *flags, str(self.source)],
                    cwd=self.root, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.snapshot(), before)

    def test_empty_file_and_directory_fail_without_output(self):
        empty = self.root / "empty.md"
        empty.write_text("# No observations\n", encoding="utf-8")
        for path in (empty, self.source):
            with self.subTest(path=path):
                before = self.snapshot()
                code, _, errors = self.convert(path)
                self.assertEqual(code, 1)
                self.assertIn("no observations", errors)
                self.assertEqual(self.snapshot(), before)

    def test_archive_membership_nested_files_and_maximum_id_floor(self):
        self.out = self.root / "observation-log"
        self.write_record(identifier=2)
        self.write_record(
            self.source / "archive" / "2025" / "old.md", identifier=120,
            status="declined", resolved="2026-08-05", resolution="Not supported",
        )
        (self.source / "archive" / ".id-floor").write_text("800\n", encoding="utf-8")
        floor_source = self.root / "historical"
        floor_source.mkdir()
        (floor_source / ".id-floor").write_text("1500\n", encoding="utf-8")
        (floor_source / "old-log.md").write_text(self.monolith(identifier=1700), encoding="utf-8")
        second_floor = self.root / "another-floor"
        second_floor.mkdir()
        (second_floor / ".id-floor").write_text("1600\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        code, _, errors = self.run_main(
            "--convert", self.source, "--out", self.out,
            "--id-floor-from", floor_source, "--id-floor-from", second_floor,
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual((self.out / "archive" / ".id-floor").read_text(), "1700\n")
        self.assertTrue((self.out / "archive" / "0120-keep-the-evidence.md").exists())
        self.assertFalse((self.out / "archive" / "2025").exists())
        self.assertFalse((self.out / "0120-keep-the-evidence.md").exists())
        self.assertEqual(self.records()[120][0]["resolved"], "2026-08-05")
        self.assertEqual(self.records()[120][0]["resolution"], "Not supported")
        self.assertEqual(
            self.records()[120][0]["migration_provenance"]["source"],
            str(self.source / "archive" / "2025" / "old.md"),
        )
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        from observer import entry_paths
        self.assertEqual(len(entry_paths(self.out.parent, include_archive=True)), 2)

    def test_archive_floor_included_for_individual_source(self):
        path = self.write_record()
        (self.source / "archive").mkdir()
        (self.source / "archive" / ".id-floor").write_text("900\n", encoding="utf-8")
        code, _, errors = self.convert(path)
        self.assertEqual(code, 0, errors)
        self.assertEqual((self.out / "archive" / ".id-floor").read_text(), "900\n")

    def test_nested_archived_source_retains_ancestor_floor(self):
        log = self.source / "observation-log"
        path = self.write_record(
            log / "archive" / "2025" / "entry.md",
            status="actioned", resolved="2026-08-02", resolution="Confirmed applied",
        )
        (log / "archive" / ".id-floor").write_text("900\n", encoding="utf-8")
        code, _, errors = self.convert(path)
        self.assertEqual(code, 0, errors)
        self.assertEqual((self.out / "archive" / ".id-floor").read_text(), "900\n")
        self.assertTrue((self.out / "archive" / "0001-keep-the-evidence.md").exists())

    def test_unrelated_archive_ancestor_does_not_archive_active_inputs(self):
        project = self.root / "archive" / "some-project"
        project.mkdir(parents=True)
        unrelated = project.parent / "unrelated.md"
        unrelated.write_text("Not an observation; never an implicit floor source.\n", encoding="utf-8")
        (project.parent / ".id-floor").write_text("9000\n", encoding="utf-8")
        target = project / TARGET
        target.parent.mkdir(parents=True)
        target.write_text("Existing guidance.\n", encoding="utf-8")
        source = project / "active.log"
        source.write_text(self.monolith(), encoding="utf-8")
        code, _, errors = self.run_main(
            "--workspace", project, "--convert", source, "--out", self.out
        )
        self.assertEqual(code, 0, errors)
        self.assertTrue((self.out / "0001-legacy-entry.md").exists())
        self.assertEqual((self.out / "archive" / ".id-floor").read_text(), "1\n")
        self.assertNotIn("source_archive", self.records()[1][0]["migration_provenance"])
        self.out = self.root / "broader-workspace-output"
        code, _, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        self.assertTrue((self.out / "0001-legacy-entry.md").exists())
        self.assertEqual((self.out / "archive" / ".id-floor").read_text(), "1\n")

    def test_selected_log_directory_bounds_archive_membership(self):
        source = self.root / "archive" / "project" / "legacy-log"
        self.write_record(source / "active.md")
        self.write_record(
            source / "archive" / "year" / "month" / "archived.md", identifier=2,
            status="declined", resolved="2026-08-02", resolution="Unsupported",
        )
        code, _, errors = self.convert(source)
        self.assertEqual(code, 0, errors)
        self.assertTrue((self.out / "0001-keep-the-evidence.md").exists())
        self.assertTrue((self.out / "archive" / "0002-keep-the-evidence.md").exists())
        self.assertFalse((self.out / "archive" / "year").exists())

    def test_explicit_archive_directory_outputs_flat_archive(self):
        archive = self.source / "archive"
        self.write_record(
            archive / "year" / "entry.md",
            status="declined", resolved="2026-08-02", resolution="Unsupported",
        )
        code, _, errors = self.convert(archive)
        self.assertEqual(code, 0, errors)
        self.assertTrue((self.out / "archive" / "0001-keep-the-evidence.md").exists())
        self.assertEqual(
            self.records()[1][0]["migration_provenance"]["source_archive"], str(archive)
        )

    def test_archived_monolith_mix_rejected_instead_of_dropped(self):
        self.write_record()
        archived = self.source / "archive" / "historical.md"
        archived.parent.mkdir()
        archived.write_text(self.monolith(identifier=50), encoding="utf-8")
        before = self.snapshot()
        code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("monolithic inputs are unsupported", errors)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_or_missing_id_floor_fails(self):
        self.write_record()
        archive = self.source / "archive"
        archive.mkdir()
        (archive / ".id-floor").write_text("not-a-number\n", encoding="utf-8")
        code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("invalid ID floor", errors)
        self.assertFalse(self.out.exists())
        (archive / ".id-floor").unlink()
        code, _, _ = self.run_main(
            "--convert", self.source, "--out", self.out, "--id-floor-from", self.root / "missing",
        )
        self.assertEqual(code, 1)
        self.assertFalse(self.out.exists())

    def test_rerun_and_existing_empty_or_nonempty_output_are_rejected(self):
        self.write_record()
        self.out.mkdir()
        before = self.snapshot()
        code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("destination already exists", errors)
        self.assertEqual(self.snapshot(), before)
        self.out.rmdir()
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        before = self.snapshot()
        code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("destination already exists", errors)
        self.assertEqual(self.snapshot(), before)

    def test_output_within_source_is_rejected(self):
        self.write_record()
        before = self.snapshot()
        code, _, errors = self.run_main("--convert", self.source, "--out", self.source / "converted")
        self.assertEqual(code, 1)
        self.assertIn("must not be inside", errors)
        self.assertEqual(self.snapshot(), before)

    def test_unreadable_input_subdirectory_fails_instead_of_being_skipped(self):
        self.write_record()
        before = self.snapshot()

        def denied_walk(path, onerror=None, **kwargs):
            onerror(PermissionError("unreadable archive"))
            return iter(())

        with mock.patch.object(migrate.os, "walk", side_effect=denied_walk):
            code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("unreadable archive", errors)
        self.assertEqual(self.snapshot(), before)

    def test_staging_failure_cleans_only_own_staging_and_creates_no_output(self):
        self.write_record()
        before = self.snapshot()
        with mock.patch.object(migrate, "exclusive_write", side_effect=OSError("simulated write failure")):
            code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("simulated write failure", errors)
        self.assertEqual(self.snapshot(), before)

    def test_partial_publication_failure_removes_own_files_and_new_parents(self):
        self.write_record(identifier=1)
        self.write_record(identifier=2)
        self.out = self.root / "new-parent" / "new-child" / "converted"
        actual_write = migrate.exclusive_write

        def fail_second_output(path, text):
            if path == self.out / "0002-keep-the-evidence.md":
                raise PermissionError("simulated publish failure")
            actual_write(path, text)

        before = self.snapshot()
        with mock.patch.object(migrate, "exclusive_write", side_effect=fail_second_output):
            code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("simulated publish failure", errors)
        self.assertEqual(self.snapshot(), before)

    def test_rollback_failure_reports_leftover_path_and_primary_failure(self):
        self.write_record(identifier=1)
        self.write_record(identifier=2)
        actual_write, actual_unlink = migrate.exclusive_write, Path.unlink
        retained = self.out / "0001-keep-the-evidence.md"

        def fail_publication(path, text):
            if path == self.out / "0002-keep-the-evidence.md":
                raise OSError("primary publication failure")
            actual_write(path, text)

        def fail_owned_cleanup(path, *args, **kwargs):
            if path == retained:
                raise PermissionError("owned file cleanup denied")
            return actual_unlink(path, *args, **kwargs)

        with mock.patch.object(migrate, "exclusive_write", side_effect=fail_publication):
            with mock.patch.object(Path, "unlink", fail_owned_cleanup):
                code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("primary publication failure", errors)
        self.assertIn("cleanup incomplete", errors)
        self.assertIn("owned file cleanup denied", errors)
        self.assertIn(str(retained), errors)
        self.assertTrue(retained.exists())
        self.assertFalse(list(self.root.glob(".*.migrate-*")))

    def test_staging_cleanup_failure_does_not_mask_primary_failure(self):
        self.write_record()
        with mock.patch.object(migrate, "exclusive_write", side_effect=OSError("primary stage failure")):
            with mock.patch.object(migrate.shutil, "rmtree", side_effect=PermissionError("cleanup denied")):
                code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("primary stage failure", errors)
        self.assertIn("cleanup denied", errors)
        self.assertIn("cleanup incomplete", errors)
        leftovers = list(self.root.glob(".*.migrate-*"))
        self.assertEqual(len(leftovers), 1)
        self.assertIn(str(leftovers[0]), errors)
        self.assertFalse(self.out.exists())

    def test_cleanup_failure_after_publication_reports_retained_output(self):
        self.write_record()
        with mock.patch.object(migrate.shutil, "rmtree", side_effect=PermissionError("cleanup denied")):
            code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("output published", errors)
        self.assertIn("cleanup incomplete", errors)
        self.assertIn("cleanup denied", errors)
        self.assertTrue((self.out / "0001-keep-the-evidence.md").exists())
        leftovers = list(self.root.glob(".*.migrate-*"))
        self.assertEqual(len(leftovers), 1)
        self.assertIn(str(leftovers[0]), errors)

    def test_success_does_not_attempt_removal_of_required_output_parents(self):
        self.write_record()
        self.out = self.root / "new-parent" / "new-child" / "converted"
        actual_rmdir, attempts = Path.rmdir, []

        def inspect_rmdir(path, *args, **kwargs):
            if path in (self.out.parent, self.out.parent.parent):
                attempts.append(path)
                raise OSError("required parent is intentionally nonempty")
            return actual_rmdir(path, *args, **kwargs)

        with mock.patch.object(Path, "rmdir", inspect_rmdir):
            code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        self.assertEqual(attempts, [])

    def test_publication_collision_preserves_other_writers_data(self):
        self.write_record(identifier=1)
        self.write_record(identifier=2)
        actual_write = migrate.exclusive_write
        collision = self.out / "0002-keep-the-evidence.md"

        def write_with_collision(path, text):
            if path == collision:
                path.write_text("other writer's data", encoding="utf-8")
            actual_write(path, text)

        with mock.patch.object(migrate, "exclusive_write", side_effect=write_with_collision):
            code, _, _ = self.convert()
        self.assertEqual(code, 1)
        self.assertEqual(collision.read_text(), "other writer's data")
        self.assertFalse((self.out / "0001-keep-the-evidence.md").exists())
        self.assertFalse(list(self.root.glob(".*.migrate-*")))
        self.assertTrue((self.source / "0001-legacy.md").exists())

    def test_destination_reservation_race_does_not_overwrite(self):
        self.write_record()
        actual_mkdir = Path.mkdir

        def mkdir_with_race(path, *args, **kwargs):
            if path == self.out:
                actual_mkdir(path)
                (path / "existing.txt").write_text("concurrent data", encoding="utf-8")
            return actual_mkdir(path, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", mkdir_with_race):
            code, _, errors = self.convert()
        self.assertEqual(code, 1)
        self.assertIn("destination already exists", errors)
        self.assertEqual((self.out / "existing.txt").read_text(), "concurrent data")
        self.assertFalse(list(self.root.glob(".*.migrate-*")))

    def test_invalid_legacy_metadata_remains_review_required(self):
        self.write_record(
            status="unrecognised", date="2026-02-31", siblings_checked=[],
            skill_qualifiers={"old-workflow": ["keep", "all", "qualifiers"]},
            body="Keep the entire unstructured body.\n",
        )
        code, report, errors = self.convert()
        self.assertEqual(code, 0, errors)
        data, body, _ = self.records()[1]
        self.assertEqual(data["status"], "unrecognised")
        self.assertEqual(data["date"], "2026-02-31")
        self.assertEqual(body, "Keep the entire unstructured body.\n")
        self.assertEqual(data["target_qualifiers"], {TARGET: ["keep", "all", "qualifiers"]})
        self.assertIn("needs human review: 1/1", report)
        self.assertTrue(data["related_targets_checked"].strip())
        self.assertIn("migration_note", data)

    def test_ancillary_principles_and_review_marker_are_reported_and_untouched(self):
        self.write_record()
        (self.source / "cross-cutting-principles.md").write_text("Preserve separately.\n", encoding="utf-8")
        (self.source / "last-review-date.txt").write_text("2026-08-02\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.source.iterdir()}
        code, report, errors = self.convert()
        self.assertEqual(code, 0, errors)
        self.assertIn("cross-cutting-principles.md", report)
        self.assertIn("last-review-date.txt", report)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_frontmatter_delimiter_whitespace_and_crlf_body(self):
        path = self.write_record()
        text = path.read_text(encoding="utf-8").replace("---\n", "---  \n", 1)
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        original = path.read_bytes()
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.records()[1][1], BODY)
        self.assertEqual(path.read_bytes(), original)

    def test_legacy_yaml_comments_survive_as_raw_migration_provenance(self):
        path = self.write_record()
        text = path.read_text(encoding="utf-8").replace(
            "\n---\n", "\nresolved: null  # candidate from free-text note: 2026-08-14; unconfirmed\n---\n", 1
        )
        path.write_text(text, encoding="utf-8")
        code, _, errors = self.convert()
        self.assertEqual(code, 0, errors)
        data = self.records()[1][0]
        self.assertIsNone(data["resolved"])
        self.assertEqual(data["migration_provenance"]["source_entry"], text)

    def test_explicit_workspace_from_another_current_directory(self):
        self.write_record()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "migrate-log.py"), "--convert", str(self.source),
             "--out", str(self.out), "--workspace", str(self.root),
             "--target-map", json.dumps(self.mapping)],
            cwd=self.source, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.records()[1][0]["targets"], [TARGET])

    def test_concurrent_conversions_only_one_reserves_destination(self):
        self.write_record()
        args = [
            sys.executable, str(SCRIPTS / "migrate-log.py"), "--convert", str(self.source),
            "--out", str(self.out), "--workspace", str(self.root),
            "--target-map", json.dumps(self.mapping),
        ]
        processes = [
            subprocess.Popen(args, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        results = [process.communicate(timeout=30) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1], results)
        self.assertEqual(len(self.records()), 1)
        self.assertFalse(list(self.root.glob(".*.migrate-*")))


if __name__ == "__main__":
    unittest.main()
