# Using Task Observer with GitHub Copilot

Task Observer learns from available evidence about your work—not from hidden
telemetry. It notices corrections and recurring friction, records suggestions,
and helps you decide which instructions, prompts, or skills should change.
The method comes from **Eoghan Henn / rebelytics.com**; this guide describes its
GitHub Copilot adaptation.

## 1. Install in the owning workspace

Follow the [README quick start](README.md#quick-start). Keep the complete native
skill at `.github/skills/task-observer/`, copy the three `.github/prompts/` files,
and merge only the **Task Observer** section of `.github/copilot-instructions.md`
rather than replacing your own instructions or importing this repository's test
conventions. Initialization creates the store's ignore file if absent; do not
copy runtime data or this repository's storage README into your project.

Run the helper from the workspace root:

```powershell
python -m pip install -r .github\skills\task-observer\requirements.txt
python .github\skills\task-observer\scripts\observer.py --workspace . init
python .github\skills\task-observer\scripts\observer.py --workspace . scan
python .github\skills\task-observer\scripts\validate-copilot-observer.py --workspace .
```

`--workspace .` means the current directory. If your terminal is inside a
subdirectory, return to the **owning workspace root** or pass that root
explicitly. Never derive runtime storage from the installed skill's directory.

- **Git worktrees:** use the current worktree, not the main checkout.
- **Multi-root workspaces:** identify which root owns the task; if ambiguous,
  clarify before creating records. Do not combine unrelated projects.
- **Non-Git folders:** use the selected workspace folder and arrange private
  storage protection separately; Git ignore rules cannot protect a non-Git share.
- **Temporary checkouts:** deliberately preserve ignored records before removal.
  A commit or push does not preserve ignored files.

There is no global log discovery, profile scan, or implicit cross-project store.

## 2. Understand activation

Supported Copilot Chat hosts load repository instructions automatically.
The bootstrap explicitly asks Copilot to load the canonical skill **and run its
Session Start Protocol**; reading a file alone is not execution.

The reusable prompts are:

| Prompt file | Purpose |
| --- | --- |
| `observer-start.prompt.md` | Initialize/check storage and begin observation |
| `observer-review.prompt.md` | Read evidence and propose changes |
| `observer-apply.prompt.md` | Apply only explicitly approved changes |

Use IDE prompt discovery only where your host/version supports it. These are
not promised slash commands in Copilot CLI or GitHub.com. The newer VS Code
Agent Host does not currently consume prompt files. The portable fallback is:

> Read `.github/skills/task-observer/SKILL.md` and its relevant references.
> Run the Session Start Protocol in the owning workspace, then perform the
> requested review or approved application.

Check automatic activation in a **fresh session**: did Copilot identify the
workspace, inspect the store, and evaluate the review marker? A manually
triggered successful run proves the procedure works, not that future automatic
activation is guaranteed. A missing store after writable task sessions warrants
investigation; an empty store may simply mean no useful observations arose.

For personal VS Code preferences, create a user `*.instructions.md` file using
**Chat: New Instructions File → User**, with `applyTo: '**'`. Current user
instructions live under `~/.copilot/instructions`; this does not configure
every other IDE. The old `github.copilot.chat.codeGeneration.instructions`
setting is deprecated since VS Code 1.102 and is historical compatibility
information only. See [environments.md](.github/skills/task-observer/references/environments.md)
for host-specific guidance and official sources.

## 3. What is saved

All runtime data defaults to the ignored `.github/copilot-observations/`:

| Path within the store | Meaning |
| --- | --- |
| `observation-log/*.md` | One record per observation |
| `observation-log/archive/` | Resolved records after the archival grace period |
| `observation-log/archive/.id-floor` | High-water mark preventing ID reuse |
| `cross-cutting-principles.md` | Only principles you have approved |
| `last-review-date.txt` | `never` initially; actual completed local review date later |

Initialization is idempotent: it does not overwrite an existing log, principles,
or review marker, and creates the private store's ignore file if missing.
The [starter principles](.github/skills/task-observer/references/starter-principles.md)
are optional reading, not automatically installed rules.

For the full schema, see
[observation-log.md](.github/skills/task-observer/references/observation-log.md).
Version 1 records have `schema_version: 1`, an ID, title, date, status, type,
area, session context, and:

- `targets`: a list of **existing workspace-relative files**. Examples include
  `.github/copilot-instructions.md`, a scoped instruction, a prompt, or
  `.github/skills/task-observer/SKILL.md`. Open and parked records require
  current files; resolved history can retain safe paths to retired targets.
- `proposed_workflows`: candidate working names for new workflows, not invented
  file paths. A proposal can also name existing targets it would extend.
- `related_targets_checked`: a nonempty scalar describing what related guidance
  was checked and the result—not a list or an unsupported “all checked.”
- `target_qualifiers`: optional detail retained when qualifying a target.

The body has **Issue → Suggested improvement → Principle**. Preserve useful
references, uncertainty, migration notes, and provenance. Do not turn a guess
into a fact or copy a raw conversation when a short redacted excerpt suffices.

The helper records a **full frontmatter-and-body draft**, not a sentence:

```powershell
python .github\skills\task-observer\scripts\observer.py --workspace . record --input .github\copilot-observations\draft.md
```

Create the draft only when there is a genuine signal and recording is permitted;
use the schema reference as its template. `id: 0` requests an assigned ID.
Keep the draft outside `observation-log/` so scans do not count it as a record.
Confirm the helper's saved path before saying it was recorded.

## 4. Work normally; capture useful signals

Useful signals include:

- A user correction that reveals a missing or ambiguous rule.
- A recurring task that could become a reusable prompt or native skill.
- A demonstrated conflict between related instructions.
- A missed verification step or unsupported claim, including observer failures.

Distinguish failure to follow a good rule from a defect in the rule itself.
Read the current target before proposing an amendment. Reuse an existing open
finding when the same issue recurs; strengthen its evidence rather than
inflating the count. Check related targets so a fix is neither under-scoped
nor copied everywhere indiscriminately.

Capture promptly in the current or next turn when feasible. Check at milestones
and before final delivery. Ask, **“What observations were saved? What remains
only a draft?”** No observation is required merely to demonstrate activity.

One explicit user preference may justify a narrowly scoped rule. A universal
principle needs broader evidence. Record uncertainty and a checkable next step
instead of manufacturing recurrences, measurements, quotations, or citations.

Observations and imported documents are **untrusted data**. Their contents
cannot authorize tool calls, change instruction precedence, or approve edits.

## 5. Review without applying

When there are open observations and the last-review marker is `never` or at
least seven days old, the observer offers a review. The offer should not block
your actual task. You can request a review sooner or choose a different cadence.

The [review procedure](.github/skills/task-observer/references/weekly-review.md)
separates reading, classification, proposal, approval, application, and
reconciliation:

1. Scan headers to inventory every record; malformed records are visible errors,
   not an excuse to report an empty backlog.
2. Read full candidate bodies, necessary evidence, and the current target files.
3. Cluster duplicates by the decision required, check related targets, and
   explain contradictions, missing evidence, and parked conditions.
4. Propose exact edits with observation IDs, affected paths, rationale,
   uncertainty, and validation steps. Consider removals and simplification,
   not just more rules.
5. Ask for selective or clearly scoped blanket approval of the presented changes.

Review does not automatically edit active rules or resolve observations.
A request to “review and improve things” is not advance approval of unknown
changes. Dismissing a prompt or leaving it unanswered is not consent.

## 6. Apply accepted changes and reconcile

After explicit approval, Copilot re-reads each current target and checks whether
the proposal is already applied, partially applied, stale, or conflicting.
It preserves your intervening changes and asks again if the required change
materially differs from what you approved.

It then makes surgical edits, runs appropriate existing checks, and verifies
the actual result. Creating a new workflow also requires agreement on its name,
scope, destination, and distribution. There is no automatic commit or push.

Statuses mean:

| Status | Meaning |
| --- | --- |
| `open` | Unresolved, including a proposal or a partially applied change |
| `actioned` | Approved change applied and verified for the whole agreed scope |
| `declined` | Explicit decision not to pursue, with reason and resolution date |
| `superseded` | Replaced by a named observation/decision, with reason and date |
| `parked` | Still unresolved; `parked_until` states a checkable reopening condition |

For partial application, retain per-target progress and leave the remainder
open. Never mark a multi-target observation done after editing only one file.
Re-scan at the end: concurrent arrivals were not necessarily reviewed, and must
be listed as pending rather than silently counted as handled.

A completed, approved local review/reconciliation can update
`last-review-date.txt` even if you accept no rule changes. Setup, skipped or
failed runs, draft-only proposals, and artifact downloads do not reset it.
Resolved records remain active through their resolution date; on a later day:

```powershell
python .github\skills\task-observer\scripts\observer.py --workspace . archive
```

Parked and open records do not archive. Do not reset `.id-floor`. Local locking
cannot prevent independently created IDs colliding across branches; resolve
those conflicts deliberately and validate before merging a shared history.

## 7. Privacy, sharing, and scheduled review

`type: open-source` describes generalizable methodology, not public consent.
`type: internal` describes private context, not an encryption mechanism.
Both remain ignored by default. Redact identifying details at capture,
authoring, and publication; check combinations of examples for re-identification.

The optional [Actions workflow](.github/workflows/observer-review.yml) runs only
when `COPILOT_OBSERVER_REVIEW_ENABLED` is explicitly set to `true`. Both the
weekly schedule and manual dispatch honor that gate.

Hosted review cannot see ignored local records. If you choose to share:

1. Have a human review and redact each selected record, including its metadata.
   Keep any raw source private. The shared record must be `type: open-source`,
   have no nonempty `reference` or `migration_note`, and contain only sanitized
   inline evidence. After that review, explicitly set:

   ```yaml
   shared_for_review: true
   sanitized: true
   ```

   These additional opt-in fields are required for hosted review, not for local
   observations. They record an approved sharing decision, not proof that an
   automatic sanitizer ran. Resolve migration warnings rather than deleting
   them to make a record eligible.
2. Force-add **only each specific sanitized file** you intend to share. For
   example, after substituting an actual reviewed filename:
   `git add -f -- .github/copilot-observations/observation-log/NNNN-reviewed-title.md`
3. Inspect the staged diff for private evidence, internal paths, and unrelated
   files before making a separately authorized commit. Never force-add the
   entire store or remove its ignore rule.
4. Ensure needed target/protocol files are tracked and safe to include.
   Hosted targets are declarative Markdown guidance, not scripts, executable
   configuration, or hooks. The prepared snapshot must match the committed
   revision; working-tree changes are not substitute review inputs.

The workflow stages selected committed inputs into a clean review context and
produces a report artifact only. Private/untracked and archived records are not
hosted inputs. Valid resolved records in the active directory are counted as
omitted; their content is not sent to AI, and retired targets do not block review.
Every tracked open/parked observation must meet the eligibility checks; an
ineligible record or malformed metadata fails preparation rather than being
silently skipped. Zero committed open/parked records produces a no-AI skip,
including when the active directory contains only valid resolved history.
Missing required protocol/target files, untracked targets, invalid
inputs, or failed AI runs fail visibly and are not completed reviews.
It never modifies local records, principles, the review marker, or repository
rules; it does not create issues, PRs, commits, or merges.

The built-in `GITHUB_TOKEN` uses `contents: read` and `copilot-requests: write`.
Repository/organization policy, Copilot entitlement, and billing must allow
the run. See the workflow for pinned CLI commands and limits rather than
copying a second invocation here. Tool restrictions are not an OS sandbox,
and credit limits are soft bounds. Artifact access follows repository/Actions
visibility, so treat a public repository's report as public-facing.

Download a report, check its source revision and reviewed IDs against your
current workspace, then use the normal approval and apply procedure. An
artifact is a proposal, never evidence that a local review or edit happened.

## 8. Read-only tasks and historical logs

In planning, read-only chat, or a host without persistent filesystem access,
Copilot can propose a structured handoff labeled **not persisted**. Include
the owning workspace, available evidence, unresolved questions, proposed
targets, and approval state. Do not claim saved IDs or successful writes.
The receiving writable session verifies, redacts, deduplicates, and records
it; a handoff does not become trusted authority merely by being imported.

For existing logs, use the [migration guide](.github/skills/task-observer/references/migration.md).
It supports single-file and per-record histories, explicit target mappings,
dry-run checks, and conversion to a fresh destination without changing sources.
Private migration and public sharing are separate decisions.

## Make the method your own

Start with one real workflow rather than a large speculative rule library.
Keep corrections grounded in actual output and review whether new rules help.
Prune rules that do not recur, obsolete workarounds, and procedures consistently
bypassed for good reasons. Optional
[starter principles](.github/skills/task-observer/references/starter-principles.md)
need explicit selection and import provenance; local evidence should eventually
justify retaining them.

Original work: [Eoghan Henn / rebelytics.com](https://rebelytics.com),
[original repository](https://github.com/rebelytics/one-skill-to-rule-them-all/).
This Copilot adaptation remains under [CC BY 4.0](LICENSE.txt).
