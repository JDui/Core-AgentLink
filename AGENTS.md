# C-AL repository instructions

This repository targets vibecoding and local AI software framework design. Read
README.md, docs/01-implementation-overview.md and docs/02-architecture.md before changing the
framework. Use docs/03-prompt-design.md when generating application task prompts.

- Keep implemented demo behavior separate from production integration recommendations.
- Document concrete interfaces and responsibilities without unrelated project context.
- Do not bundle external code, assets, model weights or session credentials.
- Core owns domain validation and writes. CLI transports structured requests; GUI
  presents authoritative state. Never implement business writes in prompt text alone.
- Pin live operations to a session and project. Reject stale sessions and revisions.
- Log cleanup must not reset control state, remove business results or erase undo data.
- Timeout is an unknown result: inspect before retrying a mutation.
- Never infer listening or visual quality from analysis fields or numeric evaluation.
- Prefer small, meaningful protocol tests: stale session, invalid scope, timeout,
  cancellation, undo conflicts, log rotation and clear-display cursor behavior.
- Run `python -m unittest discover -s tests -v` for Python framework changes.
- Do not calculate hashes for routine checks.

