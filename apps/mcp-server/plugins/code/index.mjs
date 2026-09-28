// Code intelligence (Phase 0 group 3), with NO persistent index -- unlike an earlier personal MCP
// tool set's code-graph tools (which the idea is taken from), this re-runs universal-ctags fresh
// on every call, scoped to the given root. Callers/callees are approximated with ripgrep rather
// than a real reference graph.
// Ported from local/mcp-extraction/tools/code-tools.mjs (Phase 1), where every tool here was
// exercised against this repo's real source.
import { readFile } from "node:fs/promises";
import { run } from "../../lib/exec.mjs";
import { ctagsJson, fuzzyMatch } from "../../lib/ctags.mjs";

function absPath(p, repoRoot) {
  return p.startsWith("/") ? p : `${repoRoot}/${p}`;
}

export default {
  description: "Symbol search, definitions and approximate callers/callees -- no persistent index, re-runs ctags/ripgrep fresh each call.",
  tools: [
    {
      name: "symbol_search",
      description: "Search for symbols (functions, classes, etc.) by name across a directory. Subsequence-fuzzy match, e.g. 'ctx' matches 'Ctx' and 'context'.",
      inputSchema: (z) => ({
        query: z.string(), root: z.string().optional().describe("relative to repo root, or absolute; default '.'"),
        kind: z.string().optional(), filePath: z.string().optional(), limit: z.number().int().positive().max(200).optional(),
      }),
      handler: async ({ query, root = ".", kind, filePath, limit = 20 }, ctx) => {
        const tags = await ctagsJson(absPath(root, ctx.repoRoot));
        let results = tags.filter((t) => fuzzyMatch(t.name, query));
        if (kind) results = results.filter((t) => t.kind === kind);
        if (filePath) results = results.filter((t) => t.path.includes(filePath));
        const total = results.length;
        results = results.slice(0, Math.max(1, Math.min(200, limit)));
        return { results: results.map((t) => ({ name: t.name, kind: t.kind, path: t.path, line: t.line, scope: t.scope ?? null })), totalBeforeLimit: total };
      },
    },
    {
      name: "symbols_in_file",
      description: "List every symbol ctags finds in one file, in file order.",
      inputSchema: (z) => ({ file: z.string() }),
      handler: async ({ file }, ctx) => {
        const tags = await ctagsJson(absPath(file, ctx.repoRoot));
        return { file, symbols: tags.sort((a, b) => a.line - b.line).map((t) => ({ name: t.name, kind: t.kind, line: t.line, scope: t.scope ?? null })) };
      },
    },
    {
      name: "symbol",
      description: "Get a specific symbol's definition location and a slice of its source (a few lines of context around the definition line).",
      inputSchema: (z) => ({ name: z.string(), root: z.string().optional(), context: z.number().int().positive().optional() }),
      handler: async ({ name, root = ".", context = 15 }, ctx) => {
        const tags = await ctagsJson(absPath(root, ctx.repoRoot));
        const matches = tags.filter((t) => t.name === name);
        if (!matches.length) throw new Error(`No symbol named '${name}' found under ${root}`);
        const out = [];
        for (const t of matches) {
          const lines = (await readFile(t.path, "utf8")).split("\n");
          const start = Math.max(0, t.line - 1 - Math.floor(context / 3));
          const end = Math.min(lines.length, t.line - 1 + context);
          out.push({ path: t.path, kind: t.kind, line: t.line, source: lines.slice(start, end).join("\n") });
        }
        return { name, matches: out };
      },
    },
    {
      name: "callers",
      description: "Approximate 'find references': ripgrep for the symbol name as a whole word. Not a real call graph -- string matches, so it can include comments, unrelated shadowed names, etc.",
      inputSchema: (z) => ({ name: z.string(), root: z.string().optional(), limit: z.number().int().positive().optional() }),
      handler: async ({ name, root = ".", limit = 50 }, ctx) => {
        const absRoot = absPath(root, ctx.repoRoot);
        // Every flag must precede `--`: rg treats everything after it as positional (pattern, then
        // paths), so a `-g` glob placed after `--` is read as a path and fails.
        const res = await run("rg", ["--json", "-w", "-g", "!node_modules", "-g", "!.git", "-g", "!bin", "-g", "!obj", "--", name, absRoot], { timeoutMs: 20_000 });
        if (res.exitCode !== 0 && res.exitCode !== 1) throw new Error(`rg failed: ${res.stderr.trim()}`);
        const matches = [];
        for (const line of res.stdout.split("\n").filter(Boolean)) {
          const obj = JSON.parse(line);
          if (obj.type !== "match") continue;
          matches.push({ path: obj.data.path.text, line: obj.data.line_number, text: obj.data.lines.text.trimEnd() });
          if (matches.length >= limit) break;
        }
        return { name, matches, note: "string matches, not a true reference graph" };
      },
    },
    {
      name: "callees",
      description: "Approximate 'what does this function call': greps the source slice of the given symbol's own body for other identifier-like calls. Rough and best-effort -- a real call graph needs a language-specific parser, which this deliberately skips.",
      inputSchema: (z) => ({ name: z.string(), root: z.string().optional(), bodyLines: z.number().int().positive().optional() }),
      handler: async ({ name, root = ".", bodyLines = 40 }, ctx) => {
        const tags = await ctagsJson(absPath(root, ctx.repoRoot));
        const match = tags.find((t) => t.name === name);
        if (!match) throw new Error(`No symbol named '${name}' found under ${root}`);
        const lines = (await readFile(match.path, "utf8")).split("\n");
        const slice = lines.slice(match.line - 1, Math.min(lines.length, match.line - 1 + bodyLines)).join("\n");
        const calls = [...new Set([...slice.matchAll(/\b([A-Za-z_][A-Za-z0-9_.]*)\s*\(/g)].map((m) => m[1]).filter((n) => n !== name))];
        return { name, path: match.path, definitionLine: match.line, approxCallees: calls };
      },
    },
  ],
};
