---
description: Review Copilot observations and propose evidence-linked instruction or workflow changes.
agent: agent
---

Load [Task Observer](../skills/task-observer/SKILL.md), then its
[review procedure](../skills/task-observer/references/weekly-review.md) and
[authoring rules](../skills/task-observer/references/skill-authoring.md).
If any required file is missing, stop the review and report it.

Read the relevant observation bodies and current targets. Group decisions by
underlying problem, check evidence and related targets, and propose exact edits
with observation IDs, rationale, uncertainty, and any unresolved work.

This is proposal-only review. Do not edit active instructions, resolve records,
change review state, or infer approval from the request to review. In a scheduled
run, return only the report; no writes, commits, issues, PRs, or merges.
