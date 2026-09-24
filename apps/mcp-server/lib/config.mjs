// Resolves the "mcp" section of terminal-stuff's layered config. The JSONC parse/merge lives in
// exactly one place (setup/tui/jsonc.py), so this shells out to `python3 -m tui.jsonc_cli
// mcp-config` -- same approach as dotfiles/tmux/apply-status-segments.sh -- instead of adding a
// third implementation. TS_MCP_CONFIG (a JSON string) overrides it for tests.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

const DEFAULTS = { enabledPlugins: ["repo"], localPluginDir: path.join(REPO_ROOT, "local", "mcp-plugins"), pluginOptions: {} };

export function loadConfig() {
  let loaded = {};
  if (process.env.TS_MCP_CONFIG) {
    loaded = JSON.parse(process.env.TS_MCP_CONFIG);
  } else {
    try {
      const out = execFileSync("python3", ["-m", "tui.jsonc_cli", "mcp-config"], {
        cwd: path.join(REPO_ROOT, "setup"), encoding: "utf8", timeout: 10000, stdio: ["ignore", "pipe", "ignore"],
      });
      loaded = JSON.parse(out);
    } catch {
      // python3 missing or config invalid: run with defaults rather than fail to start.
    }
  }
  return { ...DEFAULTS, ...loaded, pluginOptions: { ...DEFAULTS.pluginOptions, ...(loaded.pluginOptions || {}) } };
}
