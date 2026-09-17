/** Execute the real pinned OpenClaw Zod transcript classifier without the service. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { plugin } from "bun";

const [sourceArg, transcriptArg, dependencyArg] = process.argv.slice(2);
if (!sourceArg || !transcriptArg || !dependencyArg) {
  throw new Error("Usage: bun scripts/probe_openclaw.ts OPENCLAW_SOURCE TRANSCRIPT ZOD_MODULE");
}
const source = resolve(sourceArg);
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: source, encoding: "utf8" }).trim();
if (commit !== "9ca2d1dfcd161ed862a30749f40486e95d6459f1") throw new Error("upstream commit mismatch");
plugin({
  name: "resolve-unbuilt-upstream-dependencies",
  setup(build) {
    build.onResolve({ filter: /^@openclaw\/normalization-core\/record-coerce$/ }, () => ({
      path: resolve(source, "packages/normalization-core/src/record-coerce.ts"),
    }));
    build.onResolve({ filter: /^zod$/ }, () => ({ path: resolve(dependencyArg) }));
  },
});
const native = await import(resolve(source, "src/config/sessions/session-entry-codec.ts"));
const records = readFileSync(transcriptArg, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const header = native.findSessionTranscriptHeader(records);
native.assertCurrentSessionTranscriptHeader(header);
const entries = records.filter((row) => row.type !== "session");
if (!entries.every((row) => native.isIndexedSessionEntry(row))) throw new Error("upstream classifier rejected an entry");
console.log(JSON.stringify({ commit, synthetic_only: true, upstream_classifier: "passed", entries: entries.length, live_continuation: "not_tested" }));
