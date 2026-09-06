"""Hosted-review tests never install a CLI or make an AI request."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "skills" / "task-observer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import review
from observer_common import ObservationError, dump_record


class ReviewTests(unittest.TestCase):
    def setUp(self):
        private = ROOT / ".github" / "copilot-observations"
        private.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="review-test-", dir=private)
        self.addCleanup(self.clean_temporary)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "repository"
        self.workspace.mkdir()
        self.output = self.base / "prepared"
        self.tracked = {}
        self.revision = "a" * 40
        self.target = ".github/instructions/testing.instructions.md"
        self.record = ".github/copilot-observations/observation-log/0001-example.md"
        for path in (*review.REQUIRED, self.target):
            self.write(path, "# Current protocol\n\nKeep changes approved and evidence-based.\n")
        self.data = {
            "schema_version": 1,
            "id": 1,
            "title": "A repeated testing correction",
            "status": "open",
            "type": "open-source",
            "area": "testing",
            "date": "2026-09-06",
            "session_context": "Sanitized public sample task",
            "targets": [self.target],
            "proposed_workflows": [],
            "related_targets_checked": "Checked the existing test instructions.",
            "shared_for_review": True,
            "sanitized": True,
        }
        self.body = (
            "\n**Issue:**\nThe test command needed repeated correction.\n\n"
            "**Suggested improvement:**\nName the targeted command.\n\n"
            "**Principle:**\nValidate the smallest relevant scope.\n"
        )
        self.write_record()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(review, "_tracked", return_value=(self.revision, self.tracked)).start()

    def clean_temporary(self):
        for attempt in range(12):
            try:
                self.temporary.cleanup()
                return
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(min(0.1 * (attempt + 1), 1))

    def write(self, relative, contents, tracked=True, mode="100644"):
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = contents.encode("utf-8") if isinstance(contents, str) else contents
        path.write_bytes(payload)
        if tracked:
            oid = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
            self.tracked[relative] = (mode, oid)
        return path

    def write_record(self, **updates):
        self.data.update(updates)
        return self.write(self.record, dump_record(self.data, self.body))

    def write_resolved(self, identifier=2, status="actioned", **updates):
        data = dict(self.data)
        data.update(
            id=identifier, status=status, type="internal", resolved="2026-09-06",
            resolution="Historically resolved; target subsequently retired.",
            targets=[".github/instructions/retired.instructions.md"],
            reference="retired/private-evidence.md", migration_note="Retained historical mapping note.",
        )
        data.pop("shared_for_review", None)
        data.pop("sanitized", None)
        data.update(updates)
        relative = f".github/copilot-observations/observation-log/{identifier:04d}-closed.md"
        self.write(relative, dump_record(data, self.body + "\nPrivate resolved history; do not share.\n"))
        return relative

    def prepare(self):
        return review.prepare(self.workspace, self.output)

    def mock_cli(self, response="## Proposals\n\nObservation 1: defer pending more evidence.\n", code=0, stderr=""):
        mock.patch.object(review, "_ensure_isolated").start()
        mock.patch.object(review.shutil, "which", return_value=str(self.base / "copilot.exe")).start()
        mock.patch.dict(os.environ, {
            "GITHUB_TOKEN": "fake-test-token",
            "GH_TOKEN": "unrelated-secret",
            "NODE_OPTIONS": "--require=untrusted.js",
            "COPILOT_PROVIDER_BASE_URL": "https://unapproved.invalid",
            "COPILOT_CUSTOM_INSTRUCTIONS_DIRS": "untrusted",
            "COPILOT_ALLOW_ALL": "true",
        }).start()
        help_text = "\n".join(flag.split("=")[0] for flag in review.CLI_FLAGS) + "\n--max-ai-credits"
        runner = mock.patch.object(review.subprocess, "run", side_effect=[
            subprocess.CompletedProcess(["copilot", "--version"], 0, f"GitHub Copilot CLI {review.CLI_VERSION}.\n", ""),
            subprocess.CompletedProcess(["copilot", "--help"], 0, help_text, ""),
            subprocess.CompletedProcess(["copilot"], code, response, stderr),
        ]).start()
        return runner

    def test_preparation_selects_only_committed_sanitized_inputs(self):
        self.write(".github/hooks/secret.json", "credential", tracked=True)
        self.write(".github/copilot-observations/evidence/raw.txt", "private evidence", tracked=True)
        self.write(".github/copilot-observations/observation-log/0002-private.md", "malformed private", tracked=False)
        self.write(".github/copilot-observations/observation-log/archive/0003-old.md", "archived", tracked=True)
        self.write(".git/config", "credentials", tracked=False)
        manifest = self.prepare()
        expected = set(review.REQUIRED) | {self.record, self.target}
        actual = {
            path.relative_to(self.output / "input").as_posix()
            for path in (self.output / "input").rglob("*") if path.is_file()
        }
        self.assertEqual(actual, expected | {"REVIEW-MANIFEST.json"})
        self.assertEqual(set(manifest["files"]), expected)
        self.assertEqual(manifest["observations"], [{"id": 1, "path": self.record}])
        self.assertFalse((self.output / "review-report.md").exists())

    def test_empty_backlog_explicitly_skips_without_cli_or_required_protocol(self):
        self.tracked.clear()
        manifest = self.prepare()
        with mock.patch.object(review.subprocess, "run") as run:
            report = review.invoke(self.output)
        self.assertEqual(manifest["observations"], [])
        self.assertIn("Skipped", report.read_text(encoding="utf-8"))
        self.assertIn("no AI review was invoked", report.read_text(encoding="utf-8"))
        run.assert_not_called()

    def test_resolved_retired_targets_do_not_block_open_work(self):
        closed = [
            self.write_resolved(identifier, status)
            for identifier, status in ((2, "actioned"), (3, "declined"), (4, "superseded"))
        ]
        manifest = self.prepare()
        self.assertEqual(manifest["enumerated_count"], 4)
        self.assertEqual(manifest["observations"], [{"id": 1, "path": self.record}])
        self.assertEqual(manifest["omitted_resolved"], [
            {"id": 2, "status": "actioned"},
            {"id": 3, "status": "declined"},
            {"id": 4, "status": "superseded"},
        ])
        for relative in closed:
            self.assertNotIn(relative, manifest["files"])
            self.assertFalse((self.output / "input" / relative).exists())
        self.assertNotIn(".github/instructions/retired.instructions.md", manifest["files"])
        self.assertNotIn("retired/private-evidence.md", manifest["files"])

    def test_all_resolved_records_skip_without_cli_or_protocol_inputs(self):
        self.tracked.clear()
        self.write_resolved(1, "actioned")
        self.write_resolved(2, "declined")
        with mock.patch.object(review, "MAX_OBSERVATIONS", 0):
            manifest = self.prepare()
        with mock.patch.object(review.subprocess, "run") as run:
            report = review.invoke(self.output)
        self.assertEqual(manifest["observations"], [])
        self.assertEqual(manifest["files"], {})
        text = report.read_text(encoding="utf-8")
        self.assertIn("no committed open or parked observations", text)
        self.assertIn("Resolved records omitted: 2; IDs: 1 (actioned), 2 (declined)", text)
        self.assertIn("no AI review was invoked", text)
        run.assert_not_called()

    def test_closed_records_are_not_sent_to_model_or_proposed_again(self):
        closed = self.write_resolved(2)
        self.prepare()
        model_manifest = json.loads((self.output / "input" / "REVIEW-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertNotIn("omitted_resolved", model_manifest)
        self.assertNotIn("enumerated_count", model_manifest)
        self.assertEqual([item["id"] for item in model_manifest["observations"]], [1])
        staged_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.output / "input").rglob("*") if path.is_file()
        )
        self.assertNotIn("Private resolved history", staged_text)
        self.assertNotIn(closed, staged_text)
        self.mock_cli(response="Observation 1: proposed change only for the open item.")
        report = review.invoke(self.output).read_text(encoding="utf-8")
        self.assertIn("Resolved records omitted: 1; IDs: 2 (actioned)", report)
        self.assertNotIn("Observation 2", report.split("## Model-generated proposals", 1)[1])

    def test_resolved_records_still_require_valid_resolution_metadata(self):
        self.write_resolved(2, resolved="")
        with self.assertRaisesRegex(ObservationError, "Malformed observation.*resolved"):
            self.prepare()

    def test_unknown_status_is_not_treated_as_resolved(self):
        self.write_record(status="finished")
        with self.assertRaisesRegex(ObservationError, "Malformed observation.*status"):
            self.prepare()

    def test_parked_records_remain_selected_and_must_be_eligible(self):
        self.write_record(status="parked", parked_until="The testing framework changes")
        manifest = self.prepare()
        self.assertEqual([item["id"] for item in manifest["observations"]], [1])
        self.assertEqual(manifest["omitted_resolved"], [])
        other_output = self.base / "ineligible-parked"
        self.write_record(sanitized=False)
        with self.assertRaisesRegex(ObservationError, "Explicit"):
            review.prepare(self.workspace, other_output)

    def test_ineligible_open_record_still_fails_alongside_resolved_history(self):
        self.write_resolved(2)
        self.write_record(type="internal")
        with self.assertRaisesRegex(ObservationError, "Internal observation"):
            self.prepare()

    def test_resolved_records_have_a_separate_bounded_inventory(self):
        self.write_resolved(2)
        with mock.patch.object(review, "MAX_OBSERVATIONS", 1):
            manifest = self.prepare()
        self.assertEqual(len(manifest["observations"]), 1)
        with mock.patch.object(review, "MAX_INVENTORY_RECORDS", 1):
            with self.assertRaisesRegex(ObservationError, "inventory validation limit"):
                review.prepare(self.workspace, self.base / "oversized-inventory")

    def test_private_records_cannot_be_shared_for_hosted_review(self):
        self.write_record(type="internal")
        with self.assertRaisesRegex(ObservationError, "Internal observation"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_consent_markers_must_be_boolean_true(self):
        for field, value in (("shared_for_review", False), ("sanitized", "true")):
            with self.subTest(field=field):
                self.data.update(shared_for_review=True, sanitized=True)
                self.write_record(**{field: value})
                with self.assertRaisesRegex(ObservationError, "Explicit|must be a boolean"):
                    self.prepare()

    def test_malformed_record_is_not_silently_skipped(self):
        self.write(self.record, "---\nid: [invalid\n---\n")
        with self.assertRaises(ObservationError):
            self.prepare()

    def test_duplicate_ids_fail(self):
        second = self.record.replace("example", "duplicate")
        self.write(second, dump_record(self.data, self.body))
        with self.assertRaisesRegex(ObservationError, "Duplicate"):
            self.prepare()

    def test_unresolved_migration_is_rejected(self):
        self.write_record(migration_note="A legacy target still needs a mapping.")
        with self.assertRaisesRegex(ObservationError, "migration_note"):
            self.prepare()

    def test_raw_reference_is_never_copied_even_when_committed(self):
        reference = ".github/copilot-observations/evidence/source.md"
        self.write(reference, "Private full transcript")
        self.write_record(reference=reference)
        with self.assertRaisesRegex(ObservationError, "raw evidence"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_missing_or_untracked_reference_fails(self):
        self.write_record(reference="missing.md")
        with self.assertRaisesRegex(ObservationError, "Malformed"):
            self.prepare()
        self.write("missing.md", "raw private content", tracked=False)
        with self.assertRaisesRegex(ObservationError, "raw evidence"):
            self.prepare()

    def test_missing_required_protocol_fails(self):
        del self.tracked[review.REQUIRED[1]]
        with self.assertRaisesRegex(ObservationError, "not committed"):
            self.prepare()

    def test_missing_or_untracked_target_fails(self):
        del self.tracked[self.target]
        with self.assertRaisesRegex(ObservationError, "not committed"):
            self.prepare()
        (self.workspace / self.target).unlink()
        with self.assertRaisesRegex(ObservationError, "Malformed"):
            self.prepare()

    def test_executable_and_configuration_targets_are_rejected(self):
        for target in (
            ".github/hooks/readme.md", ".github/workflows/task.yml", "scripts/task.py",
            ".github/skills/example/scripts/task.md", ".git/config",
            "evidence/source.md", "node_modules/package/README.md",
        ):
            with self.subTest(target=target):
                self.write(target, "Do not execute this target.")
                self.write_record(targets=[target])
                with self.assertRaisesRegex(ObservationError, "Unsafe or executable"):
                    self.prepare()

    def test_executable_bit_on_markdown_is_rejected(self):
        self.tracked[self.target] = ("100755", self.tracked[self.target][1])
        with self.assertRaisesRegex(ObservationError, "Executable"):
            self.prepare()

    def test_symlink_git_mode_is_rejected(self):
        self.tracked[self.target] = ("120000", self.tracked[self.target][1])
        with self.assertRaisesRegex(ObservationError, "symlink"):
            self.prepare()

    def test_path_escape_and_shell_injection_are_data_not_commands(self):
        for target in ("../outside.md", "C:/secret.md", "docs/$(touch-pwned).md", "docs/a\nb.md"):
            with self.subTest(target=target):
                self.write_record(targets=[target])
                with self.assertRaises(ObservationError):
                    self.prepare()

    def test_changed_source_is_rejected(self):
        (self.workspace / self.target).write_text("Uncommitted replacement", encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "differs from source revision"):
            self.prepare()

    def test_windows_line_endings_match_committed_lf(self):
        original = (self.workspace / self.target).read_bytes()
        (self.workspace / self.target).write_bytes(original.replace(b"\n", b"\r\n"))
        self.prepare()
        self.assertEqual((self.output / "input" / self.target).read_bytes(), original)

    def test_binary_and_non_utf8_inputs_fail(self):
        for payload in (b"binary\0content", b"\xff"):
            with self.subTest(payload=payload):
                self.write(self.target, payload)
                with self.assertRaises(ObservationError):
                    self.prepare()

    def test_input_limits_fail_instead_of_selecting_a_subset(self):
        for limit, value in (
            ("MAX_OBSERVATIONS", 0), ("MAX_FILES", 1), ("MAX_TOTAL_BYTES", 1), ("MAX_FILE_BYTES", 1),
        ):
            with self.subTest(limit=limit), mock.patch.object(review, limit, value):
                with self.assertRaises(ObservationError):
                    self.prepare()
                self.assertFalse(self.output.exists())

    def test_output_directory_is_never_overwritten(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "already exists"):
            self.prepare()
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_success_uses_readonly_arguments_clean_environment_and_provenance(self):
        self.prepare()
        run = self.mock_cli()
        report = review.invoke(self.output, max_ai_credits=45, timeout_seconds=120)
        args, kwargs = run.call_args
        command = args[0]
        for flag in review.CLI_FLAGS:
            self.assertIn(flag, command)
        self.assertIn("-s", command)
        self.assertEqual(command[command.index("-p") + 1], review.REVIEW_PROMPT)
        self.assertEqual(command[command.index("--max-ai-credits") + 1], "45")
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 120)
        self.assertEqual(kwargs["cwd"], self.output / "input")
        self.assertNotIn("--yolo", command)
        self.assertNotIn("--allow-all-tools", command)
        for name in ("GH_TOKEN", "NODE_OPTIONS", "COPILOT_PROVIDER_BASE_URL",
                     "COPILOT_CUSTOM_INSTRUCTIONS_DIRS", "COPILOT_ALLOW_ALL"):
            self.assertNotIn(name, kwargs["env"])
        self.assertEqual(kwargs["env"]["COPILOT_HOME"], str(self.output / "cli-config"))
        self.assertEqual(kwargs["env"]["GITHUB_TOKEN"], "fake-test-token")
        text = report.read_text(encoding="utf-8")
        self.assertIn(self.revision, text)
        self.assertIn("Selected observation IDs: 1", text)
        self.assertIn("Input integrity: verified unchanged", text)
        self.assertIn("Model-generated proposals", text)
        for name in ("home", "cli-config", "scratch"):
            self.assertFalse((self.output / name).exists())

    def test_cli_error_fails_without_fabricated_report_and_redacts_token(self):
        self.prepare()
        self.mock_cli(code=1, stderr="Authentication failed for fake-test-token")
        with self.assertRaisesRegex(ObservationError, r"exit 1.*\[redacted\]"):
            review.invoke(self.output)
        self.assertFalse((self.output / "review-report.md").exists())

    def test_success_without_output_is_failure(self):
        self.prepare()
        self.mock_cli(response=" \n\t")
        with self.assertRaisesRegex(ObservationError, "no report"):
            review.invoke(self.output)

    def test_output_is_not_executed(self):
        self.prepare()
        payload = "$(touch PWNED)\n```sh\nrm -rf example\n```\n"
        run = self.mock_cli(response=payload)
        report = review.invoke(self.output)
        self.assertIn(payload.strip(), report.read_text(encoding="utf-8"))
        self.assertEqual(run.call_count, 3)
        self.assertFalse((self.output / "input" / "PWNED").exists())

    def test_output_size_is_bounded(self):
        self.prepare()
        self.mock_cli(response="x" * (review.MAX_OUTPUT_BYTES + 1))
        with self.assertRaisesRegex(ObservationError, "output byte limit"):
            review.invoke(self.output)

    def test_unsupported_flags_fail_before_paid_invocation(self):
        self.prepare()
        run = self.mock_cli()
        version = next(iter(run.side_effect))
        run.side_effect = [version, subprocess.CompletedProcess(["copilot", "--help"], 0, "old CLI", "")]
        with self.assertRaisesRegex(ObservationError, "lacks required controls"):
            review.invoke(self.output)
        self.assertEqual(run.call_count, 2)

    def test_wrong_cli_version_fails_before_ai(self):
        self.prepare()
        run = self.mock_cli()
        run.side_effect = [
            subprocess.CompletedProcess(["copilot", "--version"], 0, "GitHub Copilot CLI 1.0.84-1.\n", ""),
        ]
        with self.assertRaisesRegex(ObservationError, "Expected Copilot CLI"):
            review.invoke(self.output)
        self.assertEqual(run.call_count, 1)

    def test_version_output_can_contain_an_update_hint(self):
        self.prepare()
        run = self.mock_cli()
        entries = list(run.side_effect)
        entries[0].stdout += "Run 'copilot update' to check for updates.\n"
        run.side_effect = entries
        self.assertTrue(review.invoke(self.output).is_file())

    def test_shell_wrappers_are_refused(self):
        self.prepare()
        mock.patch.object(review, "_ensure_isolated").start()
        with mock.patch.object(review.shutil, "which", return_value=str(self.base / "copilot.cmd")):
            with self.assertRaisesRegex(ObservationError, "not a shell wrapper"):
                review.invoke(self.output)

    def test_existing_configuration_is_not_loaded_or_overwritten(self):
        self.prepare()
        run = self.mock_cli()
        config = self.output / "cli-config"
        config.mkdir()
        existing = config / "mcp-config.json"
        existing.write_text('{"untrusted": true}', encoding="utf-8")
        with self.assertRaisesRegex(ObservationError, "must not already exist"):
            review.invoke(self.output)
        self.assertEqual(existing.read_text(encoding="utf-8"), '{"untrusted": true}')
        self.assertFalse((self.output / "home").exists())
        run.assert_not_called()

    def test_timeout_fails_and_cleans_cli_state(self):
        self.prepare()
        run = self.mock_cli()
        run.side_effect = subprocess.TimeoutExpired(["copilot"], 30)
        with self.assertRaisesRegex(ObservationError, "timed out"):
            review.invoke(self.output)
        self.assertFalse((self.output / "cli-config").exists())

    def test_staged_changes_before_invocation_are_rejected(self):
        self.prepare()
        (self.output / "input" / self.target).write_text("changed", encoding="utf-8")
        with mock.patch.object(review.subprocess, "run") as run:
            with self.assertRaisesRegex(ObservationError, "integrity failure"):
                review.invoke(self.output)
        run.assert_not_called()

    def test_prepared_manifest_cannot_enable_hooks(self):
        manifest = self.prepare()
        relative = ".github/hooks/untrusted.json"
        target = self.output / "input" / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(b"{}")
        manifest["files"][relative] = hashlib.sha256(b"{}").hexdigest()
        for path in (self.output / "manifest.json", self.output / "input" / "REVIEW-MANIFEST.json"):
            path.write_bytes(review._json(manifest).encode("utf-8"))
        with self.assertRaisesRegex(ObservationError, "Unsafe prepared"):
            review.invoke(self.output)

    def test_prepared_manifest_must_include_required_protocol(self):
        manifest = self.prepare()
        del manifest["files"][review.REQUIRED[0]]
        (self.output / "manifest.json").write_bytes(review._json(manifest).encode("utf-8"))
        with self.assertRaisesRegex(ObservationError, "Incomplete prepared"):
            review.invoke(self.output)

    def test_prepared_manifest_cannot_silently_drop_observations(self):
        manifest = self.prepare()
        manifest["observations"] = []
        (self.output / "manifest.json").write_bytes(review._json(manifest).encode("utf-8"))
        with self.assertRaisesRegex(ObservationError, "prepared .*manifest"):
            review.invoke(self.output)

    def test_omission_manifest_counts_must_reconcile(self):
        self.write_resolved(2)
        manifest = self.prepare()
        manifest["omitted_resolved"] = []
        (self.output / "manifest.json").write_bytes(review._json(manifest).encode("utf-8"))
        with self.assertRaisesRegex(ObservationError, "Invalid or oversized"):
            review.invoke(self.output)

    def test_staged_side_effects_after_cli_are_rejected(self):
        self.prepare()
        run = self.mock_cli()
        version = next(iter(run.side_effect))
        help_result = next(iter(run.side_effect))
        def execute(*args, **kwargs):
            if args[0][-1] == "--version":
                return version
            if args[0][-1] == "--help":
                return help_result
            (self.output / "input" / "side-effect.md").write_text("unexpected", encoding="utf-8")
            return subprocess.CompletedProcess(args[0], 0, "Pretend success", "")
        run.side_effect = execute
        with self.assertRaisesRegex(ObservationError, "integrity failure"):
            review.invoke(self.output)
        self.assertFalse((self.output / "review-report.md").exists())

    def test_extra_empty_directory_is_detected(self):
        manifest = self.prepare()
        (self.output / "input" / "unexpected").mkdir()
        with self.assertRaisesRegex(ObservationError, "unexpected directory"):
            review._audit(self.output / "input", manifest)

    def test_git_ancestor_is_refused(self):
        self.prepare()
        (self.base / ".git").mkdir()
        with self.assertRaisesRegex(ObservationError, "outside every Git"):
            review._ensure_isolated(self.output / "input")

    def test_missing_auth_is_not_silently_downgraded(self):
        self.prepare()
        mock.patch.object(review, "_ensure_isolated").start()
        mock.patch.object(review.shutil, "which", return_value=str(self.base / "copilot.exe")).start()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ObservationError, "GITHUB_TOKEN is required"):
                review.invoke(self.output)

    def test_credit_and_timeout_limits_are_enforced(self):
        self.prepare()
        for credits, timeout in ((0, 1), (101, 1), (1, 0), (1, 601)):
            with self.subTest(credits=credits, timeout=timeout):
                with self.assertRaisesRegex(ObservationError, "Credits must"):
                    review.invoke(self.output, credits, timeout)

    def test_prepare_only_does_not_use_cli_and_sets_action_output(self):
        action_output = self.base / "action-output"
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(action_output)}):
            with mock.patch.object(review, "invoke") as invoke, contextlib.redirect_stdout(io.StringIO()):
                result = review.main([
                    "--workspace", str(self.workspace), "--output-dir", str(self.output), "--prepare-only",
                ])
        self.assertEqual(result, 0)
        invoke.assert_not_called()
        self.assertIn("ready=true", action_output.read_text(encoding="utf-8"))

    def test_cli_failure_exit_code(self):
        self.write_record(sanitized=False)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            result = review.main(["--workspace", str(self.workspace), "--output-dir", str(self.output)])
        self.assertEqual(result, 1)
        self.assertIn("Review failed", errors.getvalue())

    def test_git_probe_strips_repository_redirecting_environment(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "another-repo", "GIT_WORK_TREE": "elsewhere"}):
            with mock.patch.object(review.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
                review._git(self.workspace, "ls-tree", "HEAD")
        args, kwargs = run.call_args
        self.assertEqual(args[0][1:3], ["-C", str(self.workspace)])
        self.assertNotIn("GIT_DIR", kwargs["env"])
        self.assertNotIn("GIT_WORK_TREE", kwargs["env"])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["timeout"], 30)


class WorkflowTests(unittest.TestCase):
    def workflow(self, name):
        path = ROOT / ".github" / "workflows" / name
        return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_hosted_review_is_opt_in_artifact_only(self):
        workflow = self.workflow("observer-review.yml")
        self.assertEqual(set(workflow["on"]), {"schedule", "workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["review"]
        self.assertEqual(job["if"], "vars.COPILOT_OBSERVER_REVIEW_ENABLED == 'true'")
        self.assertEqual(job["permissions"], {"contents": "read", "copilot-requests": "write"})
        self.assertLessEqual(int(job["timeout-minutes"]), 15)
        steps = job["steps"]
        authenticated = [step for step in steps if "GITHUB_TOKEN" in step.get("env", {})]
        self.assertEqual(len(authenticated), 1)
        self.assertIn("--invoke-prepared", authenticated[0]["run"])
        upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["path"], ".observer-review/review-report.md")
        self.assertEqual(upload["with"]["retention-days"], "7")
        for step in steps:
            if "uses" in step:
                self.assertRegex(step["uses"], r"^actions/[a-z-]+@[0-9a-f]{40}$")
        checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["persist-credentials"], "false")
        self.assertEqual(checkout["with"]["path"], "repository")

    def test_ci_covers_windows_linux_with_native_commands(self):
        workflow = self.workflow("validate-observer.yml")
        self.assertEqual(set(workflow["on"]), {"push", "pull_request"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["validate"]
        self.assertEqual(set(job["strategy"]["matrix"]["os"]), {"ubuntu-latest", "windows-latest"})
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        self.assertIn("python -m unittest discover -s tests", commands)
        self.assertIn("python .github/skills/task-observer/scripts/validate-copilot-observer.py --workspace .", commands)
        self.assertIn(".github/skills/task-observer/requirements.txt", commands)
        for step in job["steps"]:
            if "uses" in step:
                self.assertRegex(step["uses"], r"^actions/[a-z-]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
