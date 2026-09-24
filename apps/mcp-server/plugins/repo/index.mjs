// Built-in "repo" plugin: read-only facts about this terminal-stuff checkout. Also the reference
// for writing a plugin -- inputSchema is a function receiving zod, so plugins need no imports.
import { execFileSync } from "node:child_process";

const git = (root, ...args) => execFileSync("git", ["-C", root, ...args], { encoding: "utf8" }).trim();

export default {
  description: "Read-only facts about the terminal-stuff repo.",
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
  ],
};
