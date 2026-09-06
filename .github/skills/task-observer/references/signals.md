# Observation signals

Read when deciding whether something warrants a record. Record an actual
reusable gap, not every task mistake. The observer remains attentive during
execution, review, corrections, and discussion of the process itself.

## Useful signals

- An explicit user correction reveals a missing convention or edge case.
- Repeated manual steps suggest a reusable `.github/prompts/*.prompt.md`.
- A multi-step methodology could become a native `.github/skills/<name>/` skill.
- Copilot violates a documented rule: investigate retrieval or enforcement
  rather than adding louder duplicate instructions.
- A proven technique improves an existing workflow.
- Related instruction/prompt files disagree on a shared rule.
- Rules conflict, repeat, or never apply: propose pruning or a narrower scope.
- The observer misses a correction, loses evidence, or records the wrong target.

One explicit general preference can justify a candidate; recurrence requires
multiple actual instances. Keep a hypothesis separate from an observed fact.
Do not import another user's experience as local evidence.

## Generalization check

Would the lesson help another task with the same conventions? Does it identify a
missing rule or reusable workflow rather than just fix this output? What evidence
supports its scope? Does an existing instruction already cover it? Look up
related observations before duplicating them.

Repository-specific conventions are legitimate internal targets; not every
lesson must apply to every repository. Keep their scope explicit. A preference
for one project does not authorize a global instruction.

## Do not log

Skip casual exchanges, isolated non-generalizable changes, documented preferences
that add no new enforcement insight, unrelated external defects, speculative
improvements without evidence, or findings whose useful detail cannot be recorded
safely. Fix task-specific issues within the current task instead.

When unrelated debugging grows beyond scope, preserve a precise problem report
with the symptom, evidence, ruled-out hypotheses, and cheapest next test. It is an
observer record only if it also reveals a reusable workflow lesson.
