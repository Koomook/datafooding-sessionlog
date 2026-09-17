# datafooding.sessionlog/v1

Status: experimental 0.1. This is one envelope for transcript and workspace-evidence sources, not a new format for each harness. An incompatible semantic change requires a new contract version.

## Envelope

`schema`, `adapter_version`, `sources`, `events`, `diagnostics`, and `rights` are required. Every source has an integer position, harness, SHA-256, byte length, and base64 bytes. No input pathname is serialized. Every event references its source and native record position (plus nested message position when needed). File order is retained; timestamps do not reorder a trace. Hash-derived event IDs distinguish repeated records by position.

Messages have a role, an authorship-evidence label, and ordered blocks. Blocks include text, reasoning, tool_call, tool_result, media, and opaque. Tool arguments retain whether they were a string or a structured value. An invalid JSON argument string remains a string. Tool results link using source call IDs; unmatched IDs are diagnostics, never silently invented calls.

Control and unknown records are events too. Native IDs and lineage pointers remain available in `native`; cross-file links are not fabricated. A compacted or forked transcript can be incomplete while its bytes are perfectly preserved. Hermes lineage's top-level flattened messages are projected once; segment records remain in the source bytes.

## Determinism and integrity

Normalize is a pure function of ordered source bytes, explicit harness choices, parser policy, and adapter version. Serialization uses UTF-8 JSON with sorted keys, compact separators, ASCII escapes, finite numbers, and one trailing LF. This is the project's canonical encoding, not a claim of RFC 8785 conformance. Floating-point JSON values have Python's representation in the projection; original numeric lexemes remain in the preserved bytes.

Validation decodes each source, checks its digest/length, reprojects it using the pinned adapter version, and requires equality with the entire envelope. This catches changed messages, IDs, diagnostics, ordering, or rights labels. A digest is integrity evidence, not proof of who produced a log.

Strict parsing rejects malformed JSON, duplicate object keys, non-finite values, non-object records, and unrecognized source formats. `--preserve-invalid` retains malformed records as opaque events with diagnostics. Unknown object record types are always preserved. Resource limits bound input bytes and JSON nesting; truncated writes are never quietly completed.

## Three different round trips

1. **Source-byte restoration:** standard → original source, exact hash equality. Includes line endings, whitespace, missing final newline, unknown fields, and malformed records admitted explicitly.
2. **Conversation translation:** standard → target-shaped text/tool subset → standard. Export includes a machine-readable loss ledger. Source lineage, model context, policies, encrypted reasoning, metadata, and runtime state may not survive.
3. **Harness continuation:** a real harness resumes successfully with equivalent behavior. This requires runtime/version/context/tool validation and is **not guaranteed** by JSON parsing or either round trip above.

`restore` never writes to an agent's session store automatically. `translate` is strict by default; `--allow-loss` explicitly accepts its report. It does not execute tools or start an agent.

## Start and end evidence

Capture uses the same envelope with the `state` source adapter. The native state document names its phase, root identity, Git HEAD/status/index/worktree fingerprints, selected file hashes, lockfile hashes, explicit SQLite logical snapshots, tool-version evidence, and coverage gaps. End capture links the exact initial envelope digest and records argv/exit status/output hashes for explicitly supplied checks.

A hash inventory can detect drift; it cannot restore contents. `--include-content` additionally preserves selected file bytes. SQLite capture uses a read-only transaction and a canonical logical dump; it is not a byte-identical database backup. Omitted databases, external APIs, media, ignored files, and unprovided dependencies remain missing state. Checks passing are evidence of that check, not a declaration of task success.

No current time enters canonical state. Optional observation time is supplied explicitly with `--at`. Host versions and command outputs are observed inputs, so they can legitimately change the snapshot. `state_sha256` covers the captured state before verification metadata; end snapshots link start by digest. Capture detects in-flight selected-file/Git changes and fails rather than claiming an atomic full-machine snapshot.

## Rights

Access, operations, evaluation, training, derivatives, resale, export, retention, revocation, and deletion are separate `unknown` values by default. Normalization grants none of them. A permission receipt belongs in an independently reviewed layer; do not label a normalized archive as training-authorized. No real payload is included in this repository.
