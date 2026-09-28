// Built-in "repo" plugin: read-only facts about this terminal-stuff checkout, plus (from Phase 1,
// local/mcp-extraction/tools/repo-tools.mjs + repo-dev-tools.mjs) a source map, filtered setup
// logs, a health probe, read-only git, a hub build, a lint pass, and a tmux config reload. Idea
// taken from an earlier personal MCP tool set's own source-map/logs/health/git/build/typecheck/
// restart tools; reimplemented from scratch against this repo's own layout/doctor.sh/toolchain.
import { readdir, readFile, access } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { run } from "../../lib/exec.mjs";

const git = (root, ...args) => execFileSync("git", ["-C", root, ...args], { encoding: "utf8" }).trim();
async function exists(p) { try { await access(p); return true; } catch { return false; } }

// From CLAUDE.md's "Layout" section -- kept here as data since a model asking "what is this repo"
// shouldn't have to read CLAUDE.md in full just for this.
const SOURCE_MAP = [
  { path: "setup/", purpose: "doctor.sh (read-only health check) and setup.sh -> Python curses TUI in setup/tui/" },
  { path: "setup/tui/modules/", purpose: "one file per setup module; core.py/Ctx is the only thing allowed to mutate the system" },
  { path: "dotfiles/", purpose: "files that managed blocks in ~/.zshrc / ~/.tmux.conf source" },
  { path: "logs/", purpose: "git-ignored run logs from setup.sh (capped 25MB/50 files)" },
  { path: "apps/hub/", purpose: "C#/.NET 10 + Terminal.Gui 2.5 tabbed TUI; build output in git-ignored bin/, obj/" },
  { path: "apps/mcp-server/", purpose: "plain Node ESM pluggable MCP server; plugins under apps/mcp-server/plugins/<name>/index.mjs" },
  { path: "scripts/", purpose: "day-to-day utility scripts" },
  { path: "tmux-plugins/ nvim-plugins/ hyper-plugins/", purpose: "custom-developed plugins" },
  { path: "themes/", purpose: "palettes and editor/terminal themes" },
  { path: "config/", purpose: "layered JSONC config; setup/tui/jsonc.py <-> apps/hub/Jsonc.cs are two independent implementations of the same contract" },
  { path: "local/", purpose: "git-ignored private assets (Phase-1 standalone tooling lives at local/mcp-extraction/tools/, its own creds at local/mcp-creds.json)" },
];

export default {
  description: "Read-only facts about the terminal-stuff repo, plus its own health/build/lint and a tmux config reload.",
  tools: [
    {
      name: "info",
      description: "Repo root, current git branch, short commit hash and number of uncommitted changes.",
      handler: (_args, ctx) => ({
        root: ctx.repoRoot,
        branch: git(ctx.repoRoot, "branch", "--show-current"),
        commit: git(ctx.repoRoot, "rev-parse", "--short", "HEAD"),
        uncommitted: git(ctx.repoRoot, "status", "--porcelain").split("\n").filter(Boolean).length,
      }),
    },
    {
      name: "list_modules",
      description: "List the setup modules' source files under setup/tui/modules.",
      inputSchema: (z) => ({ contains: z.string().optional().describe("only names containing this text") }),
      handler: async ({ contains }, ctx) => {
        const fs = await import("node:fs");
        return fs.readdirSync(`${ctx.repoRoot}/setup/tui/modules`)
          .filter((f) => f.endsWith(".py") && !f.startsWith("_") && (!contains || f.includes(contains)));
      },
    },
    {
      name: "source_map",
      description: "Layout of this repo: what each top-level directory is for. Call this first when orienting in the codebase, instead of listing directories.",
      handler: (_args, ctx) => ({ root: ctx.repoRoot, entries: SOURCE_MAP, seeAlso: "CLAUDE.md for full conventions and per-feature 'lessons learned' notes." }),
    },
    {
      name: "logs",
      description: "Read this repo's own setup logs (logs/*.log). Filters by substring/regex and returns the last N matching lines. Defaults to logs/latest.log.",
      inputSchema: (z) => ({
        file: z.string().optional().describe("log filename, or 'latest' (default)"),
        substring: z.string().optional(), regex: z.string().optional(),
        lines: z.number().int().positive().max(2000).optional(),
      }),
      handler: async ({ file = "latest", substring, regex, lines = 200 }, ctx) => {
        const logsDir = `${ctx.repoRoot}/logs`;
        const name = file === "latest" ? "latest.log" : file;
        const target = `${logsDir}/${name}`;
        let text;
        try {
          text = await readFile(target, "utf8");
        } catch (err) {
          const available = await readdir(logsDir).catch(() => []);
          throw new Error(`Could not read ${target}: ${err.message}. Available: ${available.slice(-10).join(", ")}`);
        }
        let matched = text.split("\n");
        if (substring) matched = matched.filter((l) => l.includes(substring));
        if (regex) { const re = new RegExp(regex); matched = matched.filter((l) => re.test(l)); }
        return { file: target, totalMatched: matched.length, lines: matched.slice(-Math.max(1, Math.min(2000, lines))) };
      },
    },
    {
      name: "health",
      description: "Run the read-only doctor.sh health check and return its report (what's installed, what's missing, install hints). Never installs anything.",
      inputSchema: (z) => ({ onlyMissing: z.boolean().optional(), strict: z.boolean().optional() }),
      handler: async ({ onlyMissing = false, strict = false } = {}, ctx) => {
        const args = [`${ctx.repoRoot}/setup/doctor.sh`, "--no-color"];
        if (onlyMissing) args.push("--only-missing");
        if (strict) args.push("--strict");
        const res = await run("bash", args, { timeoutMs: 60_000 });
        return { exitCode: res.exitCode, report: res.stdout, stderr: res.stderr || undefined };
      },
    },
    {
      name: "git",
      description: "Read-only git query against this repo: status, log, diff, show, or branch. Cannot commit, push, or otherwise change anything -- the subcommand allowlist enforces that, not caller discipline.",
      inputSchema: (z) => ({ subcommand: z.enum(["status", "log", "diff", "show", "branch"]), args: z.array(z.string()).optional() }),
      handler: async ({ subcommand, args = [] }, ctx) => {
        const res = await run("git", [subcommand, ...args], { cwd: ctx.repoRoot, timeoutMs: 20_000 });
        if (res.exitCode !== 0) throw new Error(`git ${subcommand} failed: ${res.stderr.trim()}`);
        return { subcommand, args, output: res.stdout };
      },
    },
    {
      name: "build",
      description: "Build apps/hub (dotnet build) and return the compiler output plus the stamped build-info (commit/dirty) on success.",
      groups: ["repo", "build"],
      handler: async (_args, ctx) => {
        const hubDir = `${ctx.repoRoot}/apps/hub`;
        const res = await run("dotnet", ["build", "-v", "quiet"], { cwd: hubDir, timeoutMs: 180_000 });
        const result = { exitCode: res.exitCode, output: (res.stdout + res.stderr).trim(), durationMs: res.durationMs };
        if (res.exitCode !== 0) return result;
        const about = await run("dotnet", ["run", "--project", `${hubDir}/hub.csproj`, "--no-build", "--", "--about"], { cwd: hubDir, timeoutMs: 30_000 })
          .catch((err) => ({ stdout: "", stderr: String(err) }));
        return { ...result, about: about.stdout.trim() || about.stderr.trim() || undefined };
      },
    },
    {
      name: "lint",
      description: "Syntax-check the repo's own scripts: bash -n on every .sh script, shellcheck too if installed, and py_compile on every setup/tui module. Read-only.",
      handler: async (_args, ctx) => {
        const findRes = await run("find", [ctx.repoRoot, "-type", "f", "-name", "*.sh", "-not", "-path", "*/node_modules/*", "-not", "-path", "*/.git/*"], { timeoutMs: 15_000 });
        const shFiles = findRes.stdout.split("\n").filter(Boolean);
        const bashResults = [];
        for (const f of shFiles) {
          const r = await run("bash", ["-n", f], { timeoutMs: 10_000 });
          if (r.exitCode !== 0) bashResults.push({ file: f, error: r.stderr.trim() });
        }
        const shellcheckAvailable = await run("sh", ["-c", "command -v shellcheck"], { timeoutMs: 5000 }).then((r) => r.exitCode === 0).catch(() => false);
        let shellcheckResults = null;
        if (shellcheckAvailable && shFiles.length) {
          const r = await run("shellcheck", shFiles, { timeoutMs: 60_000 });
          shellcheckResults = { exitCode: r.exitCode, output: r.stdout || r.stderr };
        }
        const pyRes = await run("python3", ["-m", "compileall", "-q", `${ctx.repoRoot}/setup/tui`], { timeoutMs: 30_000 });
        return {
          bashFilesChecked: shFiles.length, bashSyntaxErrors: bashResults,
          shellcheck: shellcheckAvailable ? shellcheckResults : "not installed -- skipped",
          pythonCompileOk: pyRes.exitCode === 0,
          pythonCompileOutput: pyRes.exitCode === 0 ? undefined : (pyRes.stdout + pyRes.stderr).trim(),
        };
      },
    },
    {
      name: "tmux_reload",
      description: "Re-source dotfiles/tmux/tmux.conf into the current tmux server and re-apply status segments, the way a fresh tmux start would pick up a config change without restarting the server. No-op (reports why) if no tmux server is reachable.",
      groups: ["repo", "tmux"],
      handler: async (_args, ctx) => {
        const confPath = `${ctx.repoRoot}/dotfiles/tmux/tmux.conf`;
        if (!(await exists(confPath))) throw new Error(`Missing ${confPath}`);
        const probe = await run("tmux", ["display-message", "-p", "ok"], { timeoutMs: 5000 });
        if (probe.exitCode !== 0) return { reloaded: false, reason: "no reachable tmux server (or $TMUX_TMPDIR/$TMUX point elsewhere)" };
        const src = await run("tmux", ["source-file", confPath], { timeoutMs: 10_000 });
        if (src.exitCode !== 0) throw new Error(`tmux source-file failed: ${src.stderr.trim()}`);
        const segScript = `${ctx.repoRoot}/dotfiles/tmux/apply-status-segments.sh`;
        let segments = "skipped (script not found)";
        if (await exists(segScript)) {
          const seg = await run("bash", [segScript, ctx.repoRoot], { timeoutMs: 15_000 });
          segments = seg.exitCode === 0 ? "applied" : `failed: ${seg.stderr.trim()}`;
        }
        return { reloaded: true, confPath, statusSegments: segments };
      },
    },
  ],
};
