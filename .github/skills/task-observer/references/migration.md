# Migrating historical observations into the Copilot workspace

Use this only for existing evidence. Fresh installs use
`observer.py --workspace . init`; they do not need a migration.
The canonical log is
`.github/copilot-observations/observation-log/`, separate from the native
skill at `.github/skills/task-observer/`.

The migrator reads an explicitly supplied single-file log or per-observation
directory, checks it, and converts into a **new destination directory**.
It never updates the source or merges by overwriting existing records.
Historical provider-specific text can remain in private raw evidence; preserve
history rather than rewriting it to make it look native.

## Schema changes

Every converted record uses `schema_version: 1`.

| Historical field | Copilot field |
| --- | --- |
| `skill` | `targets`: existing workspace-relative file paths, resolved by explicit mapping |
| `proposes_skill` | `proposed_workflows`: candidate working names, not invented target paths |
| `siblings_checked` | `related_targets_checked`: a nonempty scalar describing a real check |
| `skill_qualifiers` | Optional `target_qualifiers`, with original detail retained in provenance |

Preserve IDs, titles, statuses, type, area, dates, session context, parked
conditions, resolution dates/reasons, references, and unrecognized metadata.
The body retains **Issue / Suggested improvement / Principle** and its evidence.
Original metadata and source details survive as migration provenance.

Valid statuses remain `open`, `actioned`, `declined`, `superseded`, and `parked`;
types remain `open-source` and `internal`. Unknown or missing metadata must be
flagged, not silently treated as resolved or omitted from a clean backlog.
A historical “actioned” label is not proof that a present-day target contains
the change—verify that separately during review.

Unmapped target names are reported and preserved in `migration_note`/provenance.
Do not guess a path from a skill name, silently turn it into a new workflow,
or fill a missing related-target check with invented activity. A warning-bearing
conversion is a **review-required staging result**, not a certified live log.

Dates require particular care: an unrelated date in a resolution narrative
is not the resolution date. Keep uncertain historical precision uncertain;
do not substitute the conversion date for an unknown event.

## Before starting

1. Confirm the owning workspace and stay in its current worktree. Do not scan
   profiles, other checkouts, or unrelated global stores. Name any additional
   known source explicitly.
2. Pause writers and tell long-running sessions that a cutover is planned.
   A quiet filesystem does not prove an idle session will not append later.
3. Make a private backup of the original records, archives, principles, review
   marker, and `.id-floor` values. Keep source files unchanged.
4. Ensure the complete native skill and its requirements are installed.
   If initialization detects an active `skill-observations/` history or
   `.github/copilot-observations/log.md`, it deliberately refuses to create a
   competing store. After pausing writers and obtaining approval, retire that
   source intact to an explicitly chosen private holding location, preserving
   its contents, archives, and original location in your migration notes.
   Do not delete it or suppress the guard. Use the held source as the explicit
   migration input; the converter will not modify it. Commands below run from
   the owning workspace root once those active legacy names are retired:

   ```powershell
   python -m pip install -r .github\skills\task-observer\requirements.txt
   python .github\skills\task-observer\scripts\observer.py --workspace . init
   ```

   Initialization preserves existing state; it is not a migration or cutover.
   Confirm `.github/copilot-observations/` is ignored before putting private
   backups or staging files there. Never initialize over an inaccessible store
   by pretending it is missing.

The examples assume you deliberately placed a private source copy at
`.github/copilot-observations/legacy/log.md`. For a per-record history,
substitute its `observation-log` directory. Do not copy unrelated documents
into a directory being supplied as a per-record log.

## 1. Make explicit target mappings

Create a JSON file, for example
`.github/copilot-observations/target-map.json`, mapping actual historical
names to lists of existing files in this workspace:

```json
{
  "task-observer": [".github/skills/task-observer/SKILL.md"],
  "repository-guidance": [".github/copilot-instructions.md"]
}
```

These keys are illustrative except where they match your source. Inspect the
old records and current files to choose mappings. Values must be real
workspace-relative files; use `/` separators in metadata even when your shell
uses Windows paths. A legacy name can map to several verified targets.
Unresolved names stay flagged; an empty or guessed mapping is not a solution.

Keep private names and local paths out of a public mapping file. Mapping is a
routing decision, not approval to edit the target or publish the observation.

## 2. Dry-run before writing anything

```powershell
python .github\skills\task-observer\scripts\migrate-log.py --check .github\copilot-observations\legacy\log.md --target-map .github\copilot-observations\target-map.json
```

Read every warning and compare reported record counts with the source.
Check mode writes nothing, including bytecode or markers. Duplicate IDs, invalid input structure,
ambiguous inputs, and unsafe mappings require reconciliation before conversion.
Warnings about uncertain metadata require human review even when parsing succeeds.

For a per-record directory, include its archive subtree in the review.
Archived single-file histories are not converted as directory records: retain
those sources separately and use `--id-floor-from` to reserve their ID range.
The high-water mark protects numbering; it does **not** import archive bodies.

You can add `--id-floor-from <known-directory>` for a known earlier history,
and repeat the option for additional sources. Supply only relevant log/floor
sources, not a broad workspace containing unrelated Markdown files.

## 3. Convert into a fresh staging directory

```powershell
python .github\skills\task-observer\scripts\migrate-log.py --convert .github\copilot-observations\legacy\log.md --out .github\copilot-observations\migration-stage-1\observation-log --target-map .github\copilot-observations\target-map.json --id-floor-from .github\copilot-observations\observation-log
```

`--check` and `--convert` are mutually exclusive. `--out` must be a **new**
observation-log directory, never an existing or canonical populated destination.
Use a new stage name for a rerun; do not delete or overwrite earlier output to
make the command pass.

The converter preflights records before publishing output and preserves the
highest ID floor from converted records and explicitly included histories.
Per-record archive membership is retained; nested source archives are flattened
into the native `archive/` directory, with original paths kept in provenance.
Inspect any reported failure and
actual filesystem state before retrying; do not assume interruption left
either everything or nothing.

## 4. Reconcile staged evidence and sidecar state

Before cutover:

- Reconcile all source IDs against output IDs, including archived records.
  Compare bodies and metadata, not just file counts. Spot-check a resolved
  record, a qualifier, a parked condition, and every flagged mapping.
- Check for duplicate IDs across the proposed output, the current canonical
  log, and any separately retained archive. Independent branches can allocate
  the same number; local locking does not reconcile that history.
- Resolve `migration_note` items from real evidence. Preserve original metadata
  and the reason for the reconciliation; do not erase warnings just to pass.
- Confirm open/parked targets exist, parked conditions are checkable, and
  resolutions have valid dates and reasons. Resolved history may retain safe
  workspace-relative paths to retired targets; do not invent a replacement.
  Uncertain records remain review-required until fixed.
- Preserve **principles and the review marker separately**. They are not
  automatically imported into the runtime store by record conversion.
  Review old principles with the user, import only approved entries with their
  provenance, and merge without replacing existing user content.
- Preserve an existing review date only when its scope and actual completed
  review are verified. Otherwise retain `never`. Migration itself is not a
  review and never justifies stamping today's date.
- Confirm `.id-floor` is at least the maximum across current, staged, archived,
  and separately reserved histories. Never reset it to the active-record count.

If the canonical log already contains records, this is a **merge**, not a
rename. Stop and reconcile all histories in a fresh staging result, resolving
ID collisions and links deliberately. Passing an existing directory only as
`--id-floor-from` preserves numbering, not its records; replacing it afterward
would lose evidence.

## 5. Approve and perform cutover

Only after the staged history and sidecars are reconciled:

1. Recheck that sources have not changed since the dry-run/conversion.
2. Obtain explicit approval for the cutover and any sidecar decisions.
3. Preserve the current canonical log, even an initialized empty one, in a
   separate private holding location. Move the reviewed stage into the now
   unoccupied canonical `observation-log` path. Never overwrite or recursively
   merge the directories.
4. Apply approved principles/review-state reconciliation without losing existing
   content. Initialization before this step should have created missing sidecars.
5. Run:

   ```powershell
   python .github\skills\task-observer\scripts\observer.py --workspace . init
   python .github\skills\task-observer\scripts\observer.py --workspace . scan
   python .github\skills\task-observer\scripts\validate-copilot-observer.py --workspace .
   ```

6. Confirm IDs, active/archived counts, flags, marker, and principles are correct.
   Report migration complete only for this named workspace and verified scope.
7. Update approved local references to the canonical path, stop stale writers,
   and verify a fresh session uses the new store. Retain original files as
   private backups, not active alternate sources or forwarding stubs.

If validation fails, stop normal recording, preserve both histories, and
reconcile the reported problem. Do not clear errors or create fake records to
make the installation appear healthy.

## Rollback and sharing

For rollback, stop writers, preserve all post-cutover records and the current
ID floor, then restore the explicitly chosen backup as the sole active history.
Account for new records before restoring: reverting directories or changing
instructions alone can strand evidence. Keep backups until the migration and
any later additions are reconciled; avoid destructive cleanup.

**Private import is not public publication.** Do not rewrite raw source evidence
just to remove its history, and never automatically commit it. For hosted review,
prepare separate human-reviewed sanitized records, force-add only specifically
selected files, and review the staged diff. Never force-add the whole store.
Sources, mappings, provenance, principles, backups, and staging output can all
identify private work even when a record says `open-source`.
The [sharing checklist](weekly-review.md#scheduled-artifact-only-mode)
defines hosted eligibility, including explicit opt-in metadata; conversion
does not set those flags or grant sharing permission.
