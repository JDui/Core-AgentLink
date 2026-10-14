# C-AL repository instructions

This repository targets vibecoding and local AI software framework design. Read
README.md, docs/01-implementation-overview.md and docs/02-architecture.md before changing the
framework. Use docs/03-prompt-design.md when generating application task prompts.

Rust `crates/cal-core` owns protocol v1 and the common control lifecycle. Python
`python/cal_sdk` is a client, and examples/rust_python/adapter.py owns demo domain data.
The earlier examples/local_agentlink Python implementation is a teaching reference,
not a second canonical runtime. Read docs/07-implementation-roadmap.md and
docs/08-protocol-v1.md before changing cross-language behavior.

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
- Run `cargo test --workspace` for Rust changes; set C_AL_CLI to the built cal
  binary when running Python tests to enable real Rust/Python interoperability.
- Keep JSON Schema, Rust types and Python/C++ integration descriptions consistent.
- Do not calculate hashes for routine checks.

