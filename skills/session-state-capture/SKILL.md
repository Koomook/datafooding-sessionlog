---
name: session-state-capture
description: Capture deterministic before and after workspace evidence for an agent session, including dirty Git state, file fingerprints, selected SQLite state, dependencies, and verification results. Use when starting or closing work intended for replay, evaluation, or task-environment construction.
---

# Session state capture

Use the Sessionlog CLI to record facts. Do not reconstruct a missing starting state from the final patch or an LLM summary.

## Before work

1. Identify the authorized workspace root and the evidence directory. Keep real captures outside Git in a private directory (`0700`). Use existing authorization; do not request approval again for ordinary local capture within the task scope.
2. Ensure `sessionlog --version` is available. Install the pinned release from `https://github.com/Koomook/datafooding-sessionlog` if needed. Do not silently change a project's dependencies.
3. Before editing, run:

   ```sh
   sessionlog capture start --root /absolute/workspace \
     -o /private/evidence/start.slog.json
   ```

4. Add `--include-content` when selected file contents must be restorable and local storage is authorized. Add `--sqlite relative/database.sqlite` only for explicitly selected local databases. Database snapshots are logical data evidence, not byte-identical backups. Use `--path` for explicit files outside Git's default selection and `--exclude` for task-specific exclusions.
5. Record the exact command and selection flags. The capture reports dirty/staged Git state, file hashes, lockfile hashes, runtime versions, excluded state, and unavailable state. Symlinks are recorded without following them. Ignored data and external services are not silently discovered.

If work already started, label the capture as a late baseline in the task record. Never backdate it or call it the original start state. The optional `--at` accepts a caller-supplied time; it does not prove that observation time.

## After work

1. Use the same root, file/database selections, exclusions, and content flag as the start capture.
2. Supply the task's appropriate independent checks as explicit JSON argv arrays. Do not invent successful results or run unrelated commands. For example:

   ```sh
   sessionlog capture end --root /absolute/workspace \
     --before /private/evidence/start.slog.json \
     --verify '["uv","run","pytest"]' \
     --verify '["git","diff","--check"]' \
     -o /private/evidence/end.slog.json
   ```

3. A failed check, or a check whose state fingerprints no longer match the final state, still produces evidence and exits with code `3`. An input/capture error exits `2`. Inspect `valid_for_final_state` as well as the exit code. Retry a drift failure after the workspace settles; do not suppress it.
4. Run `sessionlog validate` on both captures. Link the start/end artifact locations in the private task record. The end document includes the exact initial envelope hash and added/removed/modified files.
5. Report what the checks establish and what remains missing. File contents plus dependencies may support a reset; hashes alone cannot. A passing test does not certify the user's complete outcome, live service state, or training rights.

## Determinism

The CLI uses no LLM or network. It does not add a clock or random ID. Identical selected state and evidence produce identical bytes. Verification output, installed versions, state changes, or a supplied timestamp are inputs that can legitimately change the fingerprint.

Keep semantic notes, candidate task boundaries, grader ideas, and human review separate from captured facts. Never upload captures or install global collection hooks without authorization for that additional action.
