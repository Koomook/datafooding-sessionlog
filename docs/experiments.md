# Experiment ledger

This file records executed checks separately from planned work. Counts and receipts are filled from test outputs, never guessed.

## Planned release gates

1. Synthetic fixtures covering all four producers: repeated normalization identical; source round trip byte exact; common projections correct; malformed/unknown/branch/tool cases covered.
2. Standard → each native-shaped exporter → standard: compare the supported conversation subset and inspect losses. Exercise available upstream readers separately.
3. Bounded local private sample: compare hashes and aggregate schema counts only. Do not publish raw text, paths, session IDs, or content-derived hashes.
4. Capture: dirty Git state, tracked/deleted/untracked files, symlinks, exclusions, lockfiles, SQLite, linked end evidence, failed check, and mid-capture drift.
5. CI on macOS and Linux; public installation smoke test; deployed product route readback.

Evidence receipts and observed limitations will be appended as these execute.
