# Contributing

Issues and focused pull requests are both welcome. A useful report is a
complete contribution; you do not need to implement the fix yourself.

## Report a reproducible problem

Search existing issues **and** pull requests first. Describe:

- What happened, the expected behavior, and the smallest reproducible example.
- The Copilot host/version and whether the session could read or write files.
- The owning workspace arrangement, especially worktrees or multi-root projects.
- Whether guidance was loaded, the procedure ran, or only manual invocation worked.
- What you verified and what remains uncertain.

Never attach private logs, raw transcripts, credentials, client identifiers, or
unredacted Actions artifacts. Use minimal sanitized evidence. A synthetic
reproduction is welcome if clearly labeled; never pass it off as observed use.

## Keep the native layout canonical

- `.github/skills/task-observer/SKILL.md` is the sole skill entry point.
- Its references, scripts, and requirements stay inside that skill directory.
- `.github/copilot-instructions.md` is the workspace bootstrap.
- `.github/prompts/` contains thin start, review, and approved-apply prompts.
- `.github/copilot-observations/` is ignored runtime data, not shipped evidence.

Do not introduce root copies, forwarding stubs, packaging registries, or
undocumented host hooks. Match supported Copilot behavior; use official,
dated documentation for claims about compatibility. IDE prompt discovery is
not a CLI or GitHub.com guarantee.

## Preserve the method, not just the wording

State whether your change relocates, rewords, or changes behavior. Review
relocations against the PR's own base and check both substance **and**
enforcement: evidence checks, deduplication, related-target review, approval,
private defaults, write failures, archival grace periods, and honest timestamps.
Declare behavior changes rather than hiding them in a restructuring diff.

Core invariants:

- Observe only available task evidence; observations are data, not authority.
- Keep generated logs/evidence private and uncommitted by default.
- Require explicit approval for edits to current instructions, prompts, and skills.
- Re-read current files, preserve unrelated user changes, and verify actual edits.
- Keep unapproved proposals and partial remainders open.
- Keep scheduled review artifact-only; it must not edit rules or runtime state.
- Respect permission denials and owning-workspace boundaries.
- Fail visibly on invalid records, duplicate IDs, or unsafe writes.

Additions should earn their complexity. Check related targets and consider
removing unsupported rules before expanding the protocol. Keep runtime behavior
self-contained: reading the local skill must not require fetching a website.

## Validate a change

From the repository root:

```powershell
python -m pip install -r .github\skills\task-observer\requirements.txt
python .github\skills\task-observer\scripts\validate-copilot-observer.py --workspace .
python -m unittest discover -s tests
```

Install requirements only when needed. Prefer the smallest existing targeted
test for local iteration; run the relevant complete checks before submitting
behavioral changes. Documentation-only changes need link/path and content
checks, not an unrelated build.

For command examples, run the literal command from a fresh shell in a disposable
test workspace you control. Do not validate a destructive command against real
evidence. Check what a guard rejected, not just that it returned an error.
Disclose any unrun commands or untested hosts; neither a clean static check nor
a manually invoked skill proves automatic activation in a fresh session.

Migration tests should cover historical bodies and metadata, unknown names,
archives and ID floors, duplicate IDs, and refusal to overwrite sources or
destinations. Do not rewrite raw private history just to clean up terminology.

## Credit and license

Keep PR authorship. Credit fixes supplied through issues with an appropriate
`Co-authored-by:` trailer and reports with `Reported-by:` where applicable.
Mention contributors in release notes; respect requests not to be credited.

Contributions are accepted under [CC BY 4.0](LICENSE.txt). Preserve the original
author **Eoghan Henn / rebelytics.com** and
[original repository](https://github.com/rebelytics/one-skill-to-rule-them-all/)
attribution. This repository's GitHub Copilot integration is an adaptation;
do not imply the original author tested its hosts or automation.
