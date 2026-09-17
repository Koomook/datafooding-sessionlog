# Sessionlog

One deterministic, reversible record for agent sessions.

We want the lessons of real agent work to remain useful when models and harnesses change. The failures a company has already found should become repeatable evaluations instead of disappearing into a conversation archive. Sessionlog is the first step: preserve requests, actions, observations, and before/after evidence in one inspectable format. A transcript alone is not an RL environment.

**macOS first.** Claude Code, Codex, OpenClaw transcript exports, and Hermes session exports share one `datafooding.sessionlog/v1` contract. The converter runs locally, uses no LLM, and makes no network requests.

## Install

```sh
uv tool install git+https://github.com/Koomook/datafooding-sessionlog.git
sessionlog --help
```

For development: `uv sync --locked`, then `uv run sessionlog --help`.

## What is guaranteed

- The same input bytes, harness selection, and input order produce identical standard bytes. No clock, random IDs, or absolute source paths enter normalization.
- Original bytes, unknown fields, branches, and control records survive. `restore` verifies the envelope and reconstructs the selected source byte for byte.
- Common events expose messages, content blocks, tool calls/results, reasoning, session lineage, and control records with source references. A `user` role is not proof of human authorship.
- `translate` is an explicit conversation-subset export with a loss report. It is not a promise that another harness can resume tool execution or recover missing context.
- Start/end capture records selected workspace state and links the final evidence to the initial fingerprint. Missing state is reported, not inferred.

## Quick start

```sh
sessionlog normalize --harness codex rollout.jsonl -o session.slog.json
sessionlog inspect session.slog.json
sessionlog validate session.slog.json
sessionlog restore session.slog.json --source 0 -o restored.jsonl
sessionlog roundtrip --harness codex rollout.jsonl

# Cross-harness exports require acknowledging the generated loss report.
sessionlog translate session.slog.json --target claude-code \
  --allow-loss -o conversation.jsonl --report losses.json

# Keep real logs and state evidence in a private directory outside Git.
sessionlog capture start --root /path/to/workspace -o /private/evidence/start.json
sessionlog capture end --root /path/to/workspace --before /private/evidence/start.json \
  --verify '["uv","run","pytest"]' -o /private/evidence/end.json
```

`normalize` accepts multiple explicitly selected files. It never searches a home directory. Outputs are created with mode `0600` and existing files are never overwritten. Use a private filesystem location: base64 preserves secrets; it does not redact or encrypt them.

## Coverage and evidence

| Source | Supported input | Native storage caveat |
|---|---|---|
| Claude Code | Transcript JSONL, including subagent files supplied explicitly | Internal writer is closed source; official open-source SDK reader/fork code is the evidence boundary. |
| Codex | Rollout JSONL: metadata, response items, event messages, context, compaction, opaque records | Linked history, media files, and tool artifacts need separate inputs; world state is not a filesystem snapshot. |
| OpenClaw | Session transcript JSONL, versions 3 and 4; older records preserved | Current source writes SQLite. Export or extract a transcript first; this does not restore the database or runtime registry. |
| Hermes | Export JSON or JSONL containing complete sessions and messages | SQLite is canonical. Exported active messages may omit archived content; lineage segments are not counted twice. |

See [the specification](docs/specification.md), [source audit](docs/source-audit.md), [experiments](docs/experiments.md), [limitations and LLM boundary](docs/limitations.md), and [capture skill](skills/session-state-capture/SKILL.md).

## Development

```sh
uv sync --locked
uv run pytest
uv run ruff check .
```

Fixtures are synthetic. Private-log experiments publish aggregate evidence only. CI runs the contract tests on macOS and Linux; Windows path and capture behavior are not a supported claim.

