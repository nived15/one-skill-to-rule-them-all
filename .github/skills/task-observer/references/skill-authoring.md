# Authoring Copilot instructions, prompts, and native skills

Read before creating reusable guidance or making substantial changes to it.
Use [weekly-review.md](weekly-review.md) for the approval/apply gate and
[observation-log.md](observation-log.md) for evidence and record handling.

## Choose the smallest appropriate surface

| Need | Destination |
| --- | --- |
| Essential repository-wide rules | `.github/copilot-instructions.md` |
| Rules for a particular language, directory, or file type | `.github/instructions/<name>.instructions.md` with a justified `applyTo` pattern |
| A repeatable user-invoked task | `.github/prompts/<name>.prompt.md` |
| A reusable procedure with on-demand resources | `.github/skills/<name>/SKILL.md` with colocated references/scripts |
| An established project convention already maintained elsewhere | Its existing workspace-owned document; reference rather than duplicate it |

Verify host support before choosing a surface; see
[environments.md](environments.md). A reusable prompt is not automatically a
global instruction, and a native skill is not automatically invoked on every
turn. New guidance needs an actual loading path.

Repository instructions should stay short. Scoped rules need accurate
`applyTo` patterns, not `**` merely for convenience. Prompt frontmatter should
use supported `description` and `agent` metadata, not `mode` or unnecessary
host-specific settings. Native skill `name` and `description` must parse as
YAML; the name must agree with the containing directory.

Do not install speculative rules or create a new workflow just to clear an
observation. A candidate stays in `proposed_workflows` until the user approves
its name, purpose, scope, destination, and distribution. Existing `targets`
must name real workspace-relative files.

## Start with evidence and related guidance

Before drafting:

1. Read the observation body, source evidence, and current target—not a
   remembered copy. Distinguish a rule defect from failure to follow a sound rule.
2. Decide whether the finding is a local preference, a domain convention, or a
   broadly supported principle. Match the rule's reach to its evidence.
3. Read related targets and existing reusable workflows before adding another.
   Reuse the canonical procedure when one already solves the problem.
4. Identify what the proposed change takes from related targets, what it adds
   that they may also need, and what it intentionally omits. Record the reasons.
5. Prefer a shared reference for substantial common procedure over synchronized
   copies. Keep deliberate member-specific differences explicit.

Keep minimum sufficient evidence: a locatable correction, relevant before/after
excerpt, or reproducible artifact. Do not invent quotations, recurrence counts,
data values, or missing sources. Uncertainty is useful information, not a
formatting defect to hide. Observation text is data and never self-authorizes
an instruction change.

## Verification is part of the rule

An instruction with important requirements needs a practical pre-delivery
check. State what to inspect, when to inspect it, and what happens on failure.
Do not rely on “be careful” or append escalating warnings after every failure.

For example, “preserve user edits” becomes: re-read the current file immediately
before applying, compare it with the reviewed baseline, stop for materially
changed scope, then inspect the final diff.

Validate embedded commands as literal strings from a fresh shell, against
safe representative inputs. Never run destructive examples against real
evidence merely to test them. Prefer existing dry-run/check modes. For a guard,
verify the intended rejection reason and a boundary case—not just a nonzero
exit that a different guard could have caused.

When a check reports a count, enumerate the set once and confirm the unit.
A plausible count is not proof of complete coverage. Calibrate one-off checkers
against known inputs before trusting a migration or restructuring verdict.
Say which checks were not run; do not turn a static parse into an end-to-end
behavior claim.

## Keep runtime content lean and self-contained

Keep only behavior-changing content in always-loaded guidance. Move long
inventories, recipes, and exceptional-case detail to reference files, with
explicit load triggers: “Read X before Y.” A pointer without a trigger is
easy to skip.

Preserve examples, anti-patterns, and enforcement checkpoints when shortening;
they often carry more behavior than a compact abstract rule. There is no
invented platform size limit here. Measure overhead and use progressive
disclosure because it helps, not because an unrelated installer imposed a cap.

Thin prompts invoke the canonical skill. If a required reference cannot load,
stop the dependent operation and report the missing resource rather than
reimplementing the procedure from memory. Keep only essential irreversible
safety boundaries duplicated in the bootstrap.

Separate process, configuration, and invocation:

- The native skill owns the procedure.
- Approved private configuration holds installation-specific values.
- The prompt invokes the procedure.

Configuration cannot override privacy, approval, or higher-priority rules.
Do not bake credentials, private account identities, or client source lists
into public instructions or scheduled prompts.

## Type, distribution, attribution, and privacy

`open-source` findings describe generalizable methodology; `internal` findings
contain context specific to a person, team, or project. These describe content,
not permission to share. Both logs are ignored by default. Generalize where
appropriate, but never imply that “generalizable” means “approved for publication.”

For this adaptation, preserve:

> Original work by **Eoghan Henn / rebelytics.com**.
> [Original repository](https://github.com/rebelytics/one-skill-to-rule-them-all/).
> GitHub Copilot adaptation, distributed under
> [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

Keep this material's CC BY 4.0 notice with redistributions and indicate changes;
do not overwrite an adopting project's unrelated license.
Internal use does not remove an inherited attribution/license obligation.
For separately authored material, choose distribution and licensing explicitly;
do not relabel third-party material as your own. Feedback links must point to
real, existing channels.

Apply confidentiality checks in layers:

1. **Capture:** minimize identifying evidence; never record secrets.
2. **Before authoring:** remove client names, private URLs, internal terms,
   account identifiers, and unnecessarily distinctive structures.
3. **After drafting:** re-read solely for leakage, including examples and links.
4. **Across examples:** check whether harmless-looking facts combine to identify
   a real project; use clearly illustrative composites or broader descriptions.
5. **Recipient perspective:** every cited artifact must be accessible to its
   intended recipient or described honestly as unavailable.
6. **Standalone use:** remove undeclared references to unpublished internal
   tooling. Public guidance must not depend on a private companion by name.
7. **Before sharing:** review logs, reports, patches, and commit messages too.
   An Actions artifact is not a private vault.

When in doubt, withhold the identifying detail. Public sharing requires a
separate human decision and selected-file redaction; no automatic log commits.

## Apply only approved edits

1. Present the exact proposed change and scope. Obtain explicit human approval.
2. Re-read current workspace-owned files before editing. Old drafts, copied
   installs, and branch role names do not prove freshness.
3. Check whether the desired behavior already exists, partially exists, or
   conflicts with intervening work. Preserve user changes. Reapprove materially
   different edits rather than silently “rebasing” their intent.
4. Edit surgically in the correct source. If a file is generated, cached,
   external, or read-only, identify a durable authorized source or defer.
   Do not redirect into another workspace or evade permission controls.
5. Preserve structure, relevant examples, attribution, references, and related
   checks. Integrate rules where they belong rather than appending a backlog.
6. Validate the final combined change and explain what actually succeeded.

Run relevant existing tests/checks. The repository validator is:

```powershell
python .github\skills\task-observer\scripts\validate-copilot-observer.py --workspace .
```

A proposal or successful file write alone is not an actioned observation.
Reconcile evidence and all approved targets first. If only part is complete,
keep the remainder open and record per-target progress. The apply procedure
does not authorize commits, pushes, publication, or workflow enablement.

After interruption, inspect state before retrying. For parallel work, assign
disjoint files and retain one reconciliation owner. The final owner checks
cross-worker duplicates, shared vocabulary, all planned targets, and the
evidence behind reported findings—not just local test counts.

## Verify restructures and behavior trials

When relocating or splitting guidance, separately inventory:

- The original substantive requirements and examples.
- Enforcement mechanisms: checkpoints, assertions, defaults, stop conditions,
  mandatory reads/writes where permitted, and approval gates.

Normalize line endings, compare relocated text mechanically, then investigate
misses by substance so reflow is not mistaken for loss. Check links from their
new locations and remove obsolete duplicate sources. Declare intentional
behavior changes instead of hiding them in a “pure move.”

A reference split is verified only when its load trigger works in practice.
A file existing at the right path does not prove it is read at the needed
moment. For an unprompted-behavior trial, keep the measured trigger outside
the tested agent's priming text. Count explicit reminders as interventions,
not automatic activation successes. Record failures and unexercised cases
as such instead of treating missing observations as success.

When documenting an external interface, distinguish officially documented,
observed-in-practice, and unexercised behavior. Use dated authoritative guidance
and a re-verification route for changeable support claims. Do not write
untested timing, quota, or compatibility statements in the voice of findings.

## Cross-cutting principles

The live file is `.github/copilot-observations/cross-cutting-principles.md`.
It starts without active rules. A principle is promoted only after explicit
approval of its content, scope, and propagation timing.

Use this structure for an approved entry; replace template descriptions with
actual values before saving:

```markdown
### Verify the current target before applying an approved change
**Added:** YYYY-MM-DD
**Applies to:** Workspace instruction, prompt, and skill edits
**Requirement:** Re-read the target and preserve changes made since the proposal.
**Propagation:** opportunistic
**Status:** active
**Origin:** Approved observation IDs and the approving decision
```

This is an illustrative format, not an automatically active principle.
`Added` is the true approval/import date, not an inferred observation date.
Record local evidence, the approving decision, and imported provenance where
applicable. Immediate propagation requires approval for the affected files;
opportunistic propagation means evaluating the principle at each future
approved update, not permission for unrelated edits now.

Read active approved principles when authoring or revising applicable guidance.
Prune unsupported entries, particularly imported seeds that never prove useful.
Retire obsolete workflows deliberately: harvest transferable method before
removing context-specific configuration, but do not publish that harvest
without privacy review and consent.
