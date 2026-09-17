# Native source audit

Reviewed 2026-09-17. These are immutable code references, not a claim that installed user versions equal upstream HEAD. Private data is not part of this audit.

| Producer | Pinned source | Writer / reader path inspected | Consequence |
|---|---|---|---|
| Codex | [openai/codex at 8452164](https://github.com/openai/codex/tree/8452164c761c9225b2ee12c2bd1d48f818573704) | `codex-rs/rollout/src/recorder.rs`, `policy.rs`; `protocol/src/protocol.rs`, `models.rs` | Persistence policy filters events; `response_item`, `event_msg`, metadata, context, compaction, inherited history and custom tools differ. Preserve source order and all record types. |
| Claude Code SDK | [anthropics/claude-agent-sdk-python at 9d398b6](https://github.com/anthropics/claude-agent-sdk-python/tree/9d398b6b7ed8a1bf9527c8939f75a8abfa6f165b) | `_internal/sessions.py`: `_parse_transcript_entries`, `_build_conversation_chain`; `session_mutations.py`: `_build_fork_lines`; `session_import.py` | SDK reader follows `parentUuid`, filters visible messages, handles subagents, and fork writer remaps IDs. Claude Code's internal writer is not open source; its mechanism is not fully verified. |
| OpenClaw | [openclaw/openclaw at 9ca2d1d](https://github.com/openclaw/openclaw/tree/9ca2d1dfcd161ed862a30749f40486e95d6459f1) | `src/agents/sessions/session-manager-{types,codec,persistence}.ts`; `src/config/sessions/version.ts`; `session-accessor.sqlite-{read,transcript-write}.ts` | Current manager appends SQLite transcript events. Current session version is 4; version 3 remains readable. JSONL transcript shape includes session header, messages, tree links, compaction, reset, custom and leaf records. |
| Hermes | [NousResearch/hermes-agent at 6005aa1](https://github.com/NousResearch/hermes-agent/tree/6005aa1fd9aac8b1024ace50fec8cd1c85a04bae) | `hermes_state_messages.py`: `_INSERT_MESSAGE_SQL`, `get_messages`; `hermes_state_portability.py`: `_with_messages`, `export_session_lineage`; `hermes_cli/session_export.py`: `render_sessions_export` | SQLite messages are canonical. Export JSONL contains complete session objects. Lineage repeats segment messages in a flattened list. Active-message exports can exclude historical rows. |

## Product purpose provenance

The founder directed this research to local `content/` manuscripts about Harvey's task environments, Satya Nadella's model portability, and Applied Compute's repeatable work. Their shared purpose is retained learning and lower environment-construction cost. The delivery manifest identifies manuscripts prepared for delivery; independent LinkedIn publication was not verified. No private manuscript or social-account payload is copied here.

## Audit method

Read the actual record definitions and persistence/export/reader functions before implementing each adapter. Record unknown semantics as such. Native source restoration is stronger than parse success for byte preservation, and weaker than a live continuation test for behavioral compatibility. The test ledger keeps those claims separate.

