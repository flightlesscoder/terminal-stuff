// Resolves the "mcp" section of terminal-stuff's layered config. The JSONC parse/merge lives in
// exactly one place (setup/tui/jsonc.py), so this shells out to `python3 -m tui.jsonc_cli
// mcp-config` -- same approach as dotfiles/tmux/apply-status-segments.sh -- instead of adding a
// third implementation. TS_MCP_CONFIG (a JSON string) overrides it for tests.
//
// Tool visibility, in resolution order (see resolveTool below):
//   1. plugin must be in enabledPlugins
//   2. a tool's `groups` (declared by the plugin, e.g. ["network", "some-specific-device"]) vs
//      config.disabledGroups -- any overlap disables it
//   3. config.enabledTools (fully-qualified "<plugin>_<tool>") force it back on
//   4. config.disabledTools (fully-qualified) is the final word -- always wins
// disabledGroups/enabledTools/disabledTools are each the UNION of: the base config, the named
// preset selected by TS_MCP_PRESET (config.presets.<name>), and the raw TS_MCP_DISABLED_GROUPS/
// TS_MCP_ENABLED_TOOLS/TS_MCP_DISABLED_TOOLS env vars (comma-separated) -- three additive layers,
// most-specific (env var) last. This is the whole "per-session toggle" mechanism: since this
// server runs over stdio, one process per client session already exists, so a session-specific
// choice is just what env the launcher (pi's mcp.json, a shell wrapper, ...) sets for that one
// process -- no new protocol needed. System-wide defaults are whatever's saved in config.jsonc.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

const DEFAULTS = {
  enabledPlugins: ["repo"],
  localPluginDir: path.join(REPO_ROOT, "local", "mcp-plugins"),
  pluginOptions: {},
  disabledGroups: [],
  enabledTools: [],
  disabledTools: [],
  presets: {},
};

function splitEnv(name) {
  const v = process.env[name];
  return v ? v.split(",").map((s) => s.trim()).filter(Boolean) : [];
}

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
  const merged = {
    ...DEFAULTS, ...loaded,
    pluginOptions: { ...DEFAULTS.pluginOptions, ...(loaded.pluginOptions || {}) },
    presets: { ...DEFAULTS.presets, ...(loaded.presets || {}) },
  };

  const presetName = process.env.TS_MCP_PRESET;
  const preset = presetName ? merged.presets[presetName] : null;
  if (presetName && !preset) throw new Error(`TS_MCP_PRESET='${presetName}' is not a preset in mcp.presets`);

  merged.disabledGroups = [...new Set([...merged.disabledGroups, ...(preset?.disabledGroups || []), ...splitEnv("TS_MCP_DISABLED_GROUPS")])];
  merged.enabledTools = [...new Set([...merged.enabledTools, ...(preset?.enabledTools || []), ...splitEnv("TS_MCP_ENABLED_TOOLS")])];
  merged.disabledTools = [...new Set([...merged.disabledTools, ...(preset?.disabledTools || []), ...splitEnv("TS_MCP_DISABLED_TOOLS")])];
  merged.activePreset = presetName || null;
  return merged;
}

/** Whether one tool (fq = "<plugin>_<toolName>", groups = its declared groups array) survives config's filters. */
export function resolveTool(config, fq, groups) {
  let included = !groups.some((g) => config.disabledGroups.includes(g));
  if (config.enabledTools.includes(fq)) included = true;
  if (config.disabledTools.includes(fq)) included = false;
  return included;
}
