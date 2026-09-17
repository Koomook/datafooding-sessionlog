# Limits and where an LLM helps

## Deterministic core

Parsing, ordering, IDs, byte preservation, hashes, call/result association, lineage pointers, validation, and format conversion are code. An LLM adds variability and can invent links or authorship here. The core has no model dependency or credentials.

## Candidate analysis layer

Task boundaries, user intent, why a correction happened, a proposed success criterion, and a candidate environment's missing context often require semantic judgment. An LLM can propose these in a separate, source-referenced annotation file. Keep prompt/model/version, cited event IDs, uncertainty, and review outcome; never overwrite the deterministic record.

The next experiment should compare a rule baseline with an LLM on a rights-cleared, double-reviewed held-out set of at least 30 task boundaries and grader proposals. Measure agreement, unsupported claims, review minutes, and cost. Adopt only if review time falls without increasing unsupported accepted claims. No model advantage or training lift has been measured in this release.

## Toward an environment

A useful task needs an observation boundary, typed actions, transition behavior, termination, an independent grader, reset/replay semantics, and purpose-specific rights. The start snapshot helps identify what must be restored. The end snapshot binds an artifact to checks. Neither provides an external service simulator, complete filesystem history, nor reliable reward by itself.

Start with a local repository task: restore selected source and dependencies, expose a small tool set, hide independent tests, reject the broken baseline, pass the oracle, and test plausible incorrect patches. Then measure whether the second task is cheaper to build. Keep task-discovery and environment-construction success separate.

## Known constraints

- A user-role entry can contain tool output, injected context, a compacted summary, or an automated prompt. The format does not certify human authorship or completeness of all prompts.
- Harness versions change. Source commits are pinned in the audit. Unknown records survive without a claim that their semantics are understood.
- Original bytes can contain credentials and personal data. Outputs remain local, are not redacted, and must not be committed without a separate review.
- Readable thinking and encrypted reasoning are different. The converter does not recover hidden reasoning.
- Base64 storage plus the event projection costs space and memory. The first release favors auditable single-file preservation; large/compressed archives need an explicit future adapter.
- Raw SQLite files, compressed Codex archives, external media, and remote stores are not accepted as transcript inputs. Use the producer's export first. State capture's SQLite option is evidence capture, not a harness transcript importer.
- Cross-harness exports cannot recreate native tool implementations, permissions, context compaction, memory, or execution state. Parser acceptance is not continuation evidence.
- Windows is untested and not a supported platform. Linux CI tests portability, not every native desktop harness.
