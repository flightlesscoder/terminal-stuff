#!/usr/bin/env node
// terminal-stuff MCP server (stdio). Which plugins load comes from config `mcp.enabledPlugins`;
// each tool is exposed as <plugin>_<tool>, then filtered by group/tool toggles -- see
// lib/config.mjs's header for the full resolution order and how per-session overrides work
// (TS_MCP_PRESET, or the raw TS_MCP_DISABLED_GROUPS/TS_MCP_ENABLED_TOOLS/TS_MCP_DISABLED_TOOLS
// env vars -- this process is already one per client session, so that's the whole mechanism).
//   server.mjs                 serve over stdio
//   server.mjs --list-plugins  JSON: every discoverable plugin, its tools (with groups + resolved
//                              enabled state), and whether the plugin itself is enabled
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { loadConfig, resolveTool, REPO_ROOT } from "./lib/config.mjs";
import { discover, loadPlugin } from "./lib/plugins.mjs";

let config;
try {
  config = loadConfig();
} catch (e) {
  console.error(`[terminal-stuff-mcp] config error: ${e.message}`);
  process.exit(1);
}
const available = discover(config);

function toolGroups(pluginName, tool) {
  return tool.groups && tool.groups.length ? tool.groups : [pluginName];
}

if (process.argv.includes("--list-plugins")) {
  const out = [];
  for (const info of available.values()) {
    try {
      const p = await loadPlugin(info);
      const pluginEnabled = config.enabledPlugins.includes(p.name);
      out.push({
        name: p.name, source: p.source, description: p.description, enabled: pluginEnabled,
        tools: p.tools.map((t) => {
          const fq = `${p.name}_${t.name}`;
          const groups = toolGroups(p.name, t);
          return { name: fq, description: t.description, groups, enabled: pluginEnabled && resolveTool(config, fq, groups) };
        }),
      });
    } catch (e) {
      out.push({ name: info.name, source: info.source, enabled: config.enabledPlugins.includes(info.name), error: String(e.message || e), tools: [] });
    }
  }
  console.log(JSON.stringify({ activePreset: config.activePreset, plugins: out.sort((a, b) => a.name.localeCompare(b.name)) }));
  process.exit(0);
}

const server = new McpServer({ name: "terminal-stuff", version: "0.1.0" });
// Logs go to stderr only: stdout is the protocol channel.
const log = (...a) => console.error("[terminal-stuff-mcp]", ...a);
if (config.activePreset) log(`active preset: ${config.activePreset}`);

for (const name of config.enabledPlugins) {
  const info = available.get(name);
  if (!info) { log(`plugin '${name}' is enabled but not found (skipped)`); continue; }
  let plugin;
  try { plugin = await loadPlugin(info); } catch (e) { log(`plugin '${name}' failed to load: ${e.message}`); continue; }
  const ctx = { repoRoot: REPO_ROOT, config, options: config.pluginOptions[name] || {}, log };
  let registered = 0;
  for (const t of plugin.tools) {
    const fq = `${name}_${t.name}`;
    const groups = toolGroups(name, t);
    if (!resolveTool(config, fq, groups)) continue;
    registered++;
    server.registerTool(fq, {
      description: t.description,
      inputSchema: t.inputSchema ? t.inputSchema(z) : {},
    }, async (args) => {
      try {
        const r = await t.handler(args, ctx);
        return { content: [{ type: "text", text: typeof r === "string" ? r : JSON.stringify(r, null, 2) }] };
      } catch (e) {
        return { isError: true, content: [{ type: "text", text: `${fq} failed: ${e.message || e}` }] };
      }
    });
  }
  log(`loaded plugin '${name}' (${plugin.source}, ${registered}/${plugin.tools.length} tool(s) enabled)`);
}

await server.connect(new StdioServerTransport());
