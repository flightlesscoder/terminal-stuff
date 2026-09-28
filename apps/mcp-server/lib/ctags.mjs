// Shared universal-ctags runner for the "code" plugin. No persistent index -- re-runs ctags fresh
// on every call, scoped to the given root; fine at this repo's size and avoids an index going stale.
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { run } from "./exec.mjs";

export async function ctagsJson(root) {
  // Written to a temp file, not piped through stdout: this repo's whole-tree tag list is well past
  // exec.mjs's 96KB output cap, and a cap that lands mid-line breaks the JSON-lines parse below.
  // ctags has no size limit writing to disk.
  const dir = await mkdtemp(path.join(tmpdir(), "ts-ctags-"));
  const out = path.join(dir, "tags.json");
  try {
    const res = await run("ctags", [
      "--output-format=json", "--fields=+nksSl", "-R",
      "--exclude=.git", "--exclude=node_modules", "--exclude=bin", "--exclude=obj",
      "-f", out, root,
    ], { timeoutMs: 30_000 });
    if (res.exitCode !== 0) throw new Error(`ctags failed: ${res.stderr.trim()}`);
    const text = await readFile(out, "utf8");
    return text.split("\n").filter(Boolean).map((l) => JSON.parse(l));
  } finally {
    const { rm } = await import("node:fs/promises");
    await rm(dir, { recursive: true, force: true });
  }
}

/** Subsequence-fuzzy match, case-insensitive: "ctx" matches "Ctx" and "context". */
export function fuzzyMatch(name, query) {
  const n = name.toLowerCase();
  const q = query.toLowerCase();
  let i = 0;
  for (const ch of n) {
    if (i < q.length && ch === q[i]) i++;
  }
  return i === q.length;
}
