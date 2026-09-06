# Optional starter principles

This is a reference library, **not the adopter's active rules**. The live file
is `.github/copilot-observations/cross-cutting-principles.md`. Initialization
starts it without unapproved content. Read this only when the user asks about
seeding principles or accepts an offer to inspect the optional set.

These candidates preserve general lessons from the original observation method.
They do not come with local evidence and do not override the canonical safety
protocol. A useful rule in one setup may be unnecessary in another.

## Import only a selected, approved subset

1. Present applicable candidates and explain that they are unvalidated locally.
2. Let the user select the content, scope, and propagation timing.
3. Use the format in [skill-authoring.md](skill-authoring.md#cross-cutting-principles).
   Set `Added` to the actual import date, `Status` to `active`, and record
   `Origin: imported from task-observer starter set; approved by the user`
   with the approving decision. Use opportunistic propagation unless immediate
   changes have separately been approved.
4. Preserve existing principles and user edits. Do not import the whole file
   implicitly or treat an existing empty file as approval.
5. Look for local evidence during later reviews. Remove or revise candidates
   that never help; imported provenance is not a reason to keep them.

## Candidates

### 1. State reuse rights

**Applies to:** Material intended for distribution.
**Requirement:** Include clear licensing and preserve inherited license terms.
For this adaptation, keep CC BY 4.0 and the original attribution.

### 2. Preserve attribution and a feedback route

**Applies to:** Shared reusable guidance.
**Requirement:** Credit original authors and adaptations, and point readers to
an existing repository or contact route. Never invent a publication URL.

### 3. Pair important rules with verification

**Applies to:** Workflows with explicit requirements.
**Requirement:** Include a pre-delivery check of the relevant requirements and
a defined response to failure. A written rule alone is not an enforcement step.

### 4. Separate public method from private evidence

**Applies to:** Capture, authoring, and sharing.
**Requirement:** Remove client-identifying information and secrets, including
from observations, examples, reports, and commit messages. Sharing requires
separate consent.

### 5. Name concrete capabilities without inventing tools

**Applies to:** Tool-using guidance.
**Requirement:** Give the documented primary-environment mechanism and a
capability-based fallback where one exists. State when no permitted capability
is available instead of making up a tool or bypassing a denial.

### 6. Ground broad structured-output rules in representative examples

**Applies to:** Configurations, code templates, markup, and formats.
**Requirement:** Check enough real examples and boundary cases for the proposed
scope. Do not claim broad coverage from one instance or fabricate more examples
as evidence; label synthetic test fixtures clearly.

### 7. Verify delegated findings, not just formatting

**Applies to:** Delegated analysis and generation.
**Requirement:** Supply complete task inputs and ownership boundaries. Require
locatable evidence for values and judgments, then verify combined outputs,
cross-worker collisions, and unsupported claims before delivery.

### 8. Recover honestly from tool failures

**Applies to:** Interactive and file operations.
**Requirement:** Explain the blocked step plainly, preserve completed work,
and offer a permitted next step. Do not hide failure, assume user intent from
a dismissed control, or evade access restrictions.

### 9. Fit the interaction to the task

**Applies to:** Gathering user decisions.
**Requirement:** Use structured questions for structured intake and ordinary
conversation for nuanced decisions. Do not collapse a substantive approval
choice into an ambiguous button or an inferred “yes.”

### 10. Make small actionable results immediately usable

**Applies to:** Deliverables.
**Requirement:** Present a short usable summary inline. Save a durable artifact
when requested or within approved scope; in read-only contexts label it not
persisted instead of implying a file exists.

### 11. Prune as deliberately as you add

**Applies to:** All maintained guidance.
**Requirement:** Review obsolete workarounds, unrecurring rules, unused branches,
and speculative complexity for removal. Obtain approval before changing rules.

### 12. Use canonical identifiers

**Applies to:** Matching records and cross-referencing sources.
**Requirement:** Use identifiers from the source, not reconstructed names,
slugs, or guessed URLs. Keep explicit mappings where needed.

### 13. Maintain resolvable reference paths

**Applies to:** Multi-file workflows.
**Requirement:** List resources with a purpose and load trigger. Resolve them
relative to the appropriate file, distinguish resources from runtime state,
and check links when relocating content.

### 14. Schedules invoke the canonical procedure

**Applies to:** Repeated or scheduled reviews.
**Requirement:** Reference the native skill instead of copying its logic.
A schedule never supplies human approval; the observer's hosted output remains
an artifact-only proposal.

### 15. Keep invocation separate from private configuration

**Applies to:** Reusable workflows.
**Requirement:** Put process in the skill, installation-specific data in an
approved private configuration, and only the trigger in a prompt. Configuration
cannot relax approval or privacy constraints.

### 16. Inspect partial state before retrying

**Applies to:** Interrupted multi-step operations.
**Requirement:** Assume some steps may have succeeded. Inspect actual state,
preserve existing work, and retry only the unfinished authorized portion.

### 17. Offer copyable recovery artifacts

**Applies to:** Failed technical workflows.
**Requirement:** Prefer a copyable draft, patch, or permitted machine-assisted
route over asking the user to reconstruct technical content. Do not turn this
convenience preference into permission to bypass controls.

### 18. Match tool cost to the information needed

**Applies to:** Expensive interactive tools.
**Requirement:** Prefer a lighter permitted read/search mechanism when equally
effective. Escalate only for a concrete need, and stop when access is denied.

### 19. Surface network and permission prerequisites

**Applies to:** External APIs and hosted tasks.
**Requirement:** Document prerequisites using authoritative sources. Ask the
user to resolve policy or network access through the normal channel; do not
change allowlists, credentials, or permissions without authorization.

### 20. Keep behavior-changing content in runtime guidance

**Applies to:** Always-loaded instructions and skills.
**Requirement:** Move history and long inventories to supporting documentation,
but retain load-bearing examples, stop conditions, and verification steps.

### 21. Distinguish a general method from host-specific support

**Applies to:** Portable guidance.
**Requirement:** State which behavior is methodological and which requires a
particular Copilot host/version. Do not generalize one IDE's setting to all hosts.

### 22. Verify changeable platform claims

**Applies to:** Compatibility and external-interface documentation.
**Requirement:** Use current official docs and dated release guidance; separate
documented support from exercised behavior and state how to re-check it.

### 23. Check comparability before aggregating

**Applies to:** Counts, metrics, and ranked summaries.
**Requirement:** Confirm comparable populations and denominators before merging
segments. Report differences and missing inputs rather than hiding them in a
single reassuring total.

### 24. Inspect the artifact behind the signal

**Applies to:** Claims about a particular record, file, or resource.
**Requirement:** Read the relevant artifact rather than substituting an indirect
signal for proof. If unavailable, label the claim unverified.

### 25. Give only verified reasons

**Applies to:** Recommendations and findings.
**Requirement:** Each supporting reason must meet the same evidence standard
as the recommendation. One verified reason is better than a plausible second
one that has not been checked.
