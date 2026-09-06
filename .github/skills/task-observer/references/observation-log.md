# Observation storage and schema

Read before logging, validation, archival, or migration. Runtime data belongs
under the selected workspace's `.github/copilot-observations/`, separate from the
native skill. Use the workspace's current checkout, including worktrees.

```text
.github/copilot-observations/
  observation-log/
    0001-use-existing-test-runner.md
    archive/
      .id-floor
  cross-cutting-principles.md
  last-review-date.txt
```

The active directory is the index; there is no central list to rewrite.
Initialize missing state through the [observer helper](../scripts/observer.py).
`last-review-date.txt` starts as `never`. `.id-floor` starts at zero on an empty
store or the largest imported ID. Never reset it when the active log is empty.

## Record format

This is an illustrative record, not evidence from this repository. Substitute
real evidence before logging. `id: 0` is accepted only in a draft submitted to
the recording helper, which assigns a positive integer at write time.

```markdown
---
schema_version: 1
id: 0
title: Use the existing test runner
status: open
type: open-source
targets: [".github/copilot-instructions.md"]
proposed_workflows: []
related_targets_checked: "none"
area: Test commands
date: "2026-09-06"
session_context: "User correction during a test task; see the sanitized excerpt below."
parked_until:
resolved:
resolution:
reference:
---

**Issue:** The user explicitly corrected an attempted runner replacement:
"Use the test runner already configured for this project." This is one correction,
not yet evidence of recurrence.

**Suggested improvement:** Add a testing convention requiring the agent to inspect
the existing test configuration before proposing a different runner.

**Principle:** Reuse established project tooling before introducing new machinery.
```

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1` for this Copilot schema |
| `id` | Positive integer matching `NNNN-slug.md`; never reused |
| `title` | Short, nonempty description |
| `status` | `open`, `actioned`, `declined`, `superseded`, or `parked` |
| `type` | `open-source` or `internal`; not publication permission |
| `targets` | List of existing workspace-relative file paths, first primary |
| `proposed_workflows` | List of new workflow working names, separate from existing files |
| `related_targets_checked` | Nonempty account of related files considered and verdict; `none` only when none exist |
| `area` | Target section or workflow phase |
| `date` | Real logging date, `YYYY-MM-DD` |
| `session_context` | Actual task and available evidence locator; no fabricated history |
| `parked_until` | Checkable external condition, required only for `parked` |
| `resolved`, `resolution` | Required for resolved states; empty for open/parked records |
| `reference` | Optional durable workspace-relative evidence-file path |
| `target_qualifiers` | Optional mapping of targets to relevant sections |
| `migration_note` | Explicit unresolved import problem; not an approved inference |
| `shared_for_review`, `sanitized` | Optional local fields; both must be boolean `true` after explicit human redaction/sharing approval for hosted review |

At least one target or proposed workflow is required for a new record. Imported
unmapped records can retain a migration warning pending human reconciliation.
All three body sections must be nonempty. The Issue carries concrete evidence
and uncertainty; the improvement names the proposed edit; the principle states
the reusable lesson without confidential details.

## Paths and privacy

Metadata paths use `/` separators relative to the workspace, on every operating
system. CLI filesystem arguments use the operating system's path conventions.
Absolute paths, traversal outside the workspace, and linked storage are rejected.
Use a current target path rather than inventing a skill name or temporary file.

Do not keep raw chat transcripts or credentials. Minimize and sanitize quotations.
Evidence references must survive the session; if a reference cannot be safely
preserved, state what is missing rather than fabricate an account. Raw evidence
must never be selected for hosted review merely because a record references it.

## Scans, numbering, and concurrency

The session-start scan reads headers only and reports every active file.
Unrecognized/missing status and malformed metadata are review-required, not a
reason to return an empty backlog. Use full-body validation before promotion.
`scan` returns a nonzero exit status for flagged records.

The recording helper locks the local store, computes
`max(active IDs, archived IDs, .id-floor) + 1`, validates the draft, archives
eligible records, reserves the number, and creates the new file exclusively.
An ID gap after a failed write is safe; a reused ID is not. A lock conflict must
be reported. Confirm its owner has stopped before removing a stale lock.

Locks protect cooperating writers in one store, not separate Git branches.
Reconcile duplicate IDs after branch merges explicitly; preserve both records and
repair any affected cross-references. Do not overwrite one because its title is
similar. A validator failure or unexpectedly missing directory must be resolved
before proceeding, not treated as a fresh installation.

## Archival and dispositions

Only `actioned`, `declined`, or `superseded` records with a valid resolution date
before today are eligible for archival. Preserve today's records for a grace
period. Missing resolution metadata requires repair, not an invented date.
Archival moves one file without replacing a same-name destination.

Parked records stay active but outside the action queue. Re-evaluate their
recorded condition during review; reopen only when evidence shows it is met.
A vague "later" is not a park condition.

Before changing a record, re-read it and update only approved disposition fields.
Never rewrite the whole directory. For partial application, list completed
targets in the resolution and create a cross-referenced open carrier for the
remaining targets before marking the original actioned; alternatively keep the
original open with an explicit per-target progress record until all are settled.
Choose consistently and ensure outstanding work remains discoverable.

Cite the frontmatter ID and filename, never a search result's line number.
Read full bodies before citing, declining, or resolving records.
