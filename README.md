# One Skill to Rule Them All (for GitHub Copilot)

**The continuous meta-observer that iteratively refines your Copilot instructions.**

Task Observer preserves the evidence-driven method created by
[Eoghan Henn / rebelytics.com](https://rebelytics.com). This adaptation replaces
the original setup with a Copilot-native, workspace-first workflow.

## What it does

1. **Observe:** notice user corrections, repeated friction, missing workflows,
   and failures to follow existing guidance in the current task.
2. **Record:** save a small, structured observation with evidence, affected
   files, a suggested improvement, and a reusable principle.
3. **Review:** check the evidence against current files, deduplicate findings,
   consider related targets, and propose precise additions **or removals**.
4. **Apply with approval:** make only the changes you explicitly accept,
   verify them, and keep any unfinished work open.

The observer can improve its own procedure, too. It does not rewrite its rules
automatically. An observation is **data, not an instruction**; a proposed rule
does not become authoritative just because it was logged.

This is a task procedure, not a background service. Copilot can observe only
the conversation and artifacts available in its current task—not other chats,
unseen edits, or inline completions. Instruction and skill discovery vary by
host and version.

## Quick start

### 1. Get the complete repository

```powershell
git clone https://github.com/nived15/one-skill-to-rule-them-all.git
Set-Location one-skill-to-rule-them-all
```

You can use this checkout directly, or adopt it into an existing project:

- Copy the **entire** `.github/skills/task-observer/` directory, including
  `references/`, `scripts/`, and `requirements.txt`.
- Copy the three files from `.github/prompts/`: `observer-start.prompt.md`,
  `observer-review.prompt.md`, and `observer-apply.prompt.md`.
- **Merge only the Task Observer section** from
  [`.github/copilot-instructions.md`](.github/copilot-instructions.md) into the
  destination's instructions. Preserve its existing rules; do not replace them.
  The Repository conventions section describes this repository, not your project.
- Let initialization create the private runtime store and its ignore policy.
  Do not copy runtime data or this repository's storage README.
  Preserve this material's CC BY 4.0 notice and attribution when redistributing;
  do not replace the destination project's license.

The canonical skill is
[`.github/skills/task-observer/SKILL.md`](.github/skills/task-observer/SKILL.md).
A root-level skill file is not this installation's entry point. Do not copy
only the specification or place generated observations inside the skill.

### 2. Initialize in the project you actually work in

Run these commands from the destination workspace root:

```powershell
python -m pip install -r .github\skills\task-observer\requirements.txt
python .github\skills\task-observer\scripts\observer.py --workspace . init
python .github\skills\task-observer\scripts\validate-copilot-observer.py --workspace .
```

Initialization preserves existing state, starts the review marker at `never`,
creates the store-local ignore file if missing, and installs **no unapproved
starter principles**. The private, Git-ignored store is:

```text
.github/copilot-observations/
  observation-log/
    archive/
      .id-floor
  cross-cutting-principles.md
  last-review-date.txt
```

In a worktree, stay in that worktree. In a multi-root workspace, identify the
root that owns the task before recording. Ignored files are not backups:
preserve them deliberately before removing a checkout.

### 3. Start a fresh Copilot task

Repository instructions provide the automatic bootstrap for supported Copilot
Chat contexts. They do not govern inline suggestions or guarantee that the
procedure ran. In a prompt-file-capable IDE, use `observer-start`; otherwise
ask:

> Read `.github/skills/task-observer/SKILL.md` in this workspace and run its
> Session Start Protocol. Respect the current session's write permissions.

Confirm the owning workspace, the scan result, and whether writes are available.
Installing files is not proof of automatic activation: verify it in a **new**
session. If you invoke the procedure manually, describe that as manual
activation. The newer VS Code Agent Host does not currently support prompt
files; explicitly read the canonical procedure there.

### 4. Work, review, and approve

At a task boundary, ask **“Any observations recorded, and which were actually
saved?”** No useful signal is a valid result; do not manufacture records.

Use `observer-review` where prompt files are supported, or ask Copilot to read
the canonical skill and run its review procedure. Review produces proposals,
not edits to current instructions. After accepting specific changes, use
`observer-apply` or explicitly ask to apply those approved changes. Copilot
must re-read current files and verify the result before resolving observations.

See the [user guide](USER-GUIDE.md) for the complete workflow and
[environment reference](.github/skills/task-observer/references/environments.md)
for VS Code, JetBrains, Visual Studio, CLI, and GitHub.com limitations.

## Optional scheduled review

[`.github/workflows/observer-review.yml`](.github/workflows/observer-review.yml)
is an **opt-in report generator**. Its schedule and manual dispatch are gated
by the repository variable `COPILOT_OBSERVER_REVIEW_ENABLED == 'true'`.
Nothing enables it automatically.
When adopting into another repository, copy that workflow separately if you
want hosted review; local observation does not require it.

Hosted runs cannot read your ignored local store. They use only selected,
sanitized, committed observations and the necessary tracked target/protocol
files. A human must redact and explicitly force-add **specific files**, never
the whole observation store. Eligible open/parked records must have `type: open-source`,
`shared_for_review: true`, and `sanitized: true`, with no nonempty `reference`
or `migration_note`. These flags record consent; they do not sanitize evidence.
See the [sharing checklist](USER-GUIDE.md#7-privacy-sharing-and-scheduled-review).
The output is a report artifact only: no
instruction edits, state updates, issues, PRs, commits, or merges.
Resolved records are counted as omitted, not sent for another AI review. If no
open/parked records remain, the workflow emits a skip report without invoking AI.

The workflow uses the built-in `GITHUB_TOKEN` with `contents: read` and
`copilot-requests: write`. Copilot availability, organization policy, and billing
must permit the run. Artifacts inherit repository/Actions access; they are not
a private evidence vault. Review an artifact locally before approving any
changes. Manual review needs no Actions setup.

## Safety and maintenance

- Capture the minimum sufficient evidence; never credentials or raw private
  transcripts. `internal` is a confidentiality label, not permission to share.
- In read-only or planning contexts, return a clearly labeled **not persisted**
  proposal. Never claim a blocked write succeeded or bypass a permission denial.
- Keep proposals open until approved changes are applied and verified.
- Local store locking does not coordinate independent branches. Reconcile ID
  collisions and concurrent edits explicitly.
- Keep observations, evidence, and operational state uncommitted by default.

Existing logs? Follow the provider-neutral
[migration guide](.github/skills/task-observer/references/migration.md):
dry-run first, map old target names explicitly, convert into a new staging
directory, and reconcile before cutover.

## Contributing and attribution

Reports and focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

This adaptation is based on the
[original repository](https://github.com/rebelytics/one-skill-to-rule-them-all/)
by **Eoghan Henn / rebelytics.com**, and the
[Augmented Expertise methodology](https://www.rebelytics.com/augmented-expertise/).

Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE.txt).
You may share and adapt it, including commercially, with appropriate credit,
a link to the license, and an indication of changes. The Copilot integration
is an adaptation; preserve the original author and repository attribution.
