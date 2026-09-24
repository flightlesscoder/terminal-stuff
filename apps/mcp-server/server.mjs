#!/usr/bin/env node
// terminal-stuff MCP server (stdio). Which plugins load comes from config `mcp.enabledPlugins`;
// each tool is exposed as <plugin>_<tool>.
//   server.mjs                 serve over stdio
//   server.mjs --list-plugins  JSON: every discoverable plugin, its tools, and whether it's enabled
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { loadConfig, REPO_ROOT } from "./lib/config.mjs";
import { discover, loadPlugin } from "./lib/plugins.mjs";

const config = loadConfig();
const available = discover(config);

if (process.argv.includes("--list-plugins")) {
  const out = [];
  for (const info of available.values()) {
    try {
      const p = await loadPlugin(info);
      out.push({ name: p.name, source: p.source, description: p.description, enabled: config.enabledPlugins.includes(p.name),
                 tools: p.tools.map((t) => ({ name: `${p.name}_${t.name}`, description: t.description })) });
    } catch (e) {
      out.push({ name: info.name, source: info.source, enabled: config.enabledPlugins.includes(info.name), error: String(e.message || e), tools: [] });
    }
  }
  console.log(JSON.stringify(out.sort((a, b) => a.name.localeCompare(b.name))));
  process.exit(0);
}

const server = new McpServer({ name: "terminal-stuff", version: "0.1.0" });
// Logs go to stderr only: stdout is the protocol channel.
const log = (...a) => console.error("[terminal-stuff-mcp]", ...a);

for (const name of config.enabledPlugins) {
  const info = available.get(name);
  if (!info) { log(`plugin '${name}' is enabled but not found (skipped)`); continue; }
  let plugin;
  try { plugin = await loadPlugin(info); } catch (e) { log(`plugin '${name}' failed to load: ${e.message}`); continue; }
  const ctx = { repoRoot: REPO_ROOT, config, options: config.pluginOptions[name] || {}, log };
  for (const t of plugin.tools) {
    server.registerTool(`${name}_${t.name}`, {
      description: t.description,
      inputSchema: t.inputSchema ? t.inputSchema(z) : {},
    }, async (args) => {
      try {
        const r = await t.handler(args, ctx);
        return { content: [{ type: "text", text: typeof r === "string" ? r : JSON.stringify(r, null, 2) }] };
      } catch (e) {
        return { isError: true, content: [{ type: "text", text: `${name}_${t.name} failed: ${e.message || e}` }] };
      }
    });
  }
  log(`loaded plugin '${name}' (${plugin.source}, ${plugin.tools.length} tool(s))`);
}

await server.connect(new StdioServerTransport());
