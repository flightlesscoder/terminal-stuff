// Knowledge search (Phase 0 group 7), adapted from an earlier personal MCP tool set's own
// chat-search/embedding-search idea -- plain ripgrep here, no embeddings/index. Ported from
// local/mcp-extraction/tools/search-tools.mjs (Phase 1).
//
// transcript_search reads this account's own Claude Code (~/.claude/projects/**/*.jsonl) and pi
// (~/.pi/agent/sessions) session logs. That is genuinely sensitive: it's the full content of past
// conversations, potentially including anything discussed in them. Treat any result from this tool
// as private data, never something to relay elsewhere or summarize outward. It's tagged group
// "private" (in addition to "search") so it can be turned off independently of vault_search. It was
// only smoke-tested (Phase 1) against a query guaranteed to match nothing, on a Claude Code
// auto-mode PII flag when reading raw transcripts directly -- the code path runs, but was
// deliberately not exercised against a real, broadly-matching query.
import { run } from "../../lib/exec.mjs";

const VAULT_DIR = process.env.TS_VAULT_DIR || `${process.env.HOME}/apps/gitvault`;
const CLAUDE_PROJECTS_DIR = `${process.env.HOME}/.claude/projects`;
const PI_SESSIONS_DIR = `${process.env.HOME}/.pi/agent/sessions`;

async function rgSearch(root, pattern, { glob, limit = 40 } = {}) {
  const args = ["--json", "-i"];
  if (glob) args.push("-g", glob);
  args.push("--", pattern, root);
  const res = await run("rg", args, { timeoutMs: 20_000 });
  if (res.exitCode !== 0 && res.exitCode !== 1) throw new Error(`rg failed: ${res.stderr.trim()}`);
  const matches = [];
  for (const line of res.stdout.split("\n").filter(Boolean)) {
    const obj = JSON.parse(line);
    if (obj.type !== "match") continue;
    matches.push({ path: obj.data.path.text, line: obj.data.line_number, text: obj.data.lines.text.trimEnd() });
    if (matches.length >= limit) break;
  }
  return matches;
}

/** Pull every string-valued leaf out of a parsed JSON value, for grepping transcript JSONL content generically without hardcoding an exact schema. */
function extractStrings(value, out = []) {
  if (typeof value === "string") { out.push(value); return out; }
  if (Array.isArray(value)) { for (const v of value) extractStrings(v, out); return out; }
  if (value && typeof value === "object") { for (const v of Object.values(value)) extractStrings(v, out); return out; }
  return out;
}

export default {
  description: "Ripgrep-based search over the Obsidian vault and past Claude Code/pi session transcripts.",
  tools: [
    {
      name: "vault_search",
      description: `Search the Obsidian vault (${VAULT_DIR}) for a substring/regex across notes. Plain ripgrep -- no embeddings.`,
      groups: ["search"],
      inputSchema: (z) => ({ query: z.string(), limit: z.number().int().positive().optional() }),
      handler: async ({ query, limit = 20 }) => ({ root: VAULT_DIR, matches: await rgSearch(VAULT_DIR, query, { glob: "*.md", limit }) }),
    },
    {
      name: "transcript_search",
      description: "Search past Claude Code and pi session transcripts for a substring/regex. PRIVATE DATA: results are the actual content of past conversations -- treat them accordingly, never relay a result outward without the user's explicit say-so for that specific content.",
      groups: ["search", "private"],
      inputSchema: (z) => ({ query: z.string(), source: z.enum(["claude", "pi", "both"]).optional(), limit: z.number().int().positive().optional() }),
      handler: async ({ query, source = "both", limit = 20 }) => {
        const roots = [];
        if (source === "claude" || source === "both") roots.push({ dir: CLAUDE_PROJECTS_DIR, label: "claude" });
        if (source === "pi" || source === "both") roots.push({ dir: PI_SESSIONS_DIR, label: "pi" });
        const results = [];
        for (const { dir, label } of roots) {
          let matches;
          try { matches = await rgSearch(dir, query, { limit }); }
          catch (err) { results.push({ source: label, error: err.message }); continue; }
          for (const m of matches) {
            let snippet = m.text;
            try {
              const strings = extractStrings(JSON.parse(m.text));
              const hit = strings.find((s) => s.toLowerCase().includes(query.toLowerCase()));
              if (hit) snippet = hit.length > 400 ? hit.slice(0, 400) + "..." : hit;
            } catch { /* not JSON on this line -- fall back to the raw matched line */ }
            results.push({ source: label, file: m.path, line: m.line, snippet });
          }
        }
        return { matches: results.slice(0, limit), note: "PRIVATE: this is real conversation content." };
      },
    },
  ],
};
