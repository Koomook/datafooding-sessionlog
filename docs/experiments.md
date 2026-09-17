# Experiment ledger

This file records executed checks separately from planned work. Counts and receipts are filled from test outputs, never guessed.

## Planned release gates

1. Synthetic fixtures covering all four producers: repeated normalization identical; source round trip byte exact; common projections correct; malformed/unknown/branch/tool cases covered.
2. Standard → each native-shaped exporter → standard: compare the supported conversation subset and inspect losses. Exercise available upstream readers separately.
3. Bounded local private sample: compare hashes and aggregate schema counts only. Do not publish raw text, paths, session IDs, or content-derived hashes.
4. Capture: dirty Git state, tracked/deleted/untracked files, symlinks, exclusions, lockfiles, SQLite, linked end evidence, failed check, and mid-capture drift.
5. CI on macOS and Linux; public installation smoke test; deployed product route readback.

Evidence receipts and observed limitations will be appended as these execute.

## 2026-09-17 — local contract and source-reader experiments

**OBSERVED:** 47 pytest cases passed on macOS with Python 3.13, including 80 generated Unicode examples. Tests cover four source formats, all 16 source/target conversation-subset combinations, exact byte restoration, repeated canonical encoding, tampering, malformed JSON, unknown fields, tool associations, lineage, symlinks, excluded tracked secrets, SQLite capture, state drift, and failed verification.

**OBSERVED:** A bounded convenience sample of 11 local files (7 Claude Code, 4 Codex; 15,805,818 source bytes; 2,622 projected events) passed repeated normalization, deterministic reprojection validation, and exact source-byte restoration. Only aggregate counts are published in [private-sample-report.json](private-sample-report.json). There is no claim that the sample represents all versions or contains every prompt.

**OBSERVED:** Four synthetic conversation items exported from the standard were accepted by the pinned Claude SDK's real chain/visible-message reader, survived Hermes' real export renderer, and passed OpenClaw's real Zod transcript classifier. See [Python reader receipt](upstream-reader-report.json) and [OpenClaw classifier receipt](openclaw-reader-report.json). The probe scripts execute the checked-out upstream code; they do not replace the readers with lookalikes.

**NOT YET:** Codex's Rust deserializer or live continuation in any harness has not been exercised on generated conversation exports. Its export currently has source-inspected record shapes plus our own importer tests. OpenClaw service import, Hermes database import, external tool behavior, and model-quality preservation remain unverified. Original-source byte restoration is independently checked for all synthetic formats and the local sample.

### What changed because of the experiments

- OpenClaw v4's SQLite writer disproved the assumption that every current harness appends a standalone JSONL file. The adapter supports transcript exports; the native database is a separate future input.
- Hermes repeats lineage messages in `segments` and the top-level `messages`. The semantic projection reads the flattened list once.
- Codex status events can mirror model-context response items. They remain typed control observations instead of double-counted primary messages. Status-only logs retain their payload and available blocks, but primary-message analyses must inspect this coverage boundary.
- A text-only tool result is a string in one format and text blocks in another. The conversation subset joins text blocks explicitly and reports that representation change. Unknown/media-bearing results are not silently converted into text.
- A passing check can be invalidated by a later command changing the workspace. End capture now records the state before and after each check and marks whether that evidence still applies to the final state.
- Excluding a tracked secret from the file inventory is insufficient if a full Git patch still includes it. Content-bearing Git patches are restricted to selected, nonexcluded paths; a regression test exercises this case.

### Reproduce the upstream probes

Check out the exact commits in [source-audit.md](source-audit.md). Install the SDK's runtime dependencies in a disposable environment, then run `scripts/probe_upstream.py --sources /path/to/checkouts --output /private/new-directory`. This script writes synthetic exports only. For OpenClaw, use Bun and Zod 4.3.6: `bun scripts/probe_openclaw.ts /path/to/openclaw /private/new-directory/openclaw.jsonl /path/to/zod/index.js`. The probe resolves one unbuilt upstream source package through Bun, then executes the original classifier unchanged.

No LLM was used by the converter or these probes. The proposed LLM segmentation/grader study remains unexecuted; it is specified in [limitations.md](limitations.md).

## 2026-09-17 — published release

**OBSERVED:** Release commit `cc15a674f28055648e3e217c73b4454fda15460a` passed all four macOS/Linux × Python 3.11/3.13 [CI jobs](https://github.com/Koomook/datafooding-sessionlog/actions/runs/35178792097). The public Git tag installed with `uv tool install` and the installed executable passed a synthetic Codex round trip. Wheel, source archive, and SHA-256 checksums are attached to [v0.1.0](https://github.com/Koomook/datafooding-sessionlog/releases/tag/v0.1.0).

The [English](https://datafooding.ai/sessionlog/) and [Korean](https://datafooding.ai/ko/sessionlog/) product pages are live. Desktop/mobile browser review, native-format tab changes, and installation-command copy passed with no observed console errors. The website build, typecheck, and 41 existing regression tests passed. All 63 pre-existing slide/deck assets in the deployment bundle were byte-identical to the production base.

The landing implementation used a real start capture before edits and a linked end capture afterward: 226 initial files, 231 final files, and two passing checks whose state fingerprints matched the final snapshot. Evidence payloads remain outside Git. This is an executed capture workflow, not a reconstructed initial state.
