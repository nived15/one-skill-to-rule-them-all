# Observation storage

This is workspace data, not a Copilot skill discovery directory. Initialize it
with `python .github/skills/task-observer/scripts/observer.py --workspace . init`
from the workspace root. The helper creates `observation-log/archive/`, an ID
floor, empty principles, and a `never` review marker without replacing data.

Generated files are ignored by default, including raw evidence and proposals.
Ignored files can still be read by local Copilot; ignoring is not encryption.
Preserve wanted local records before removing a worktree.

For hosted review, first inspect and sanitize each selected observation and its
metadata, then explicitly force-add only that file. Never force-add this entire
directory. Do not share raw transcripts, secrets, or internal records. Already
tracked files stay tracked even when an ignore rule matches them.

After human review, shared records require `shared_for_review: true`,
`sanitized: true`, and `type: open-source`. They must contain sanitized inline
evidence, with no nonempty `reference` or unresolved `migration_note`. The flags
record an explicit sharing decision; they do not perform redaction.

Hosted review sees committed files only. Its report artifact follows repository
access permissions and is not a private evidence store. See the
[user guide](../../USER-GUIDE.md) before enabling it.
