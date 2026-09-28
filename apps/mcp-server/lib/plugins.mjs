// Plugin discovery/loading. A plugin is a directory holding index.mjs whose default export is
//   { name?, description, tools: [{ name, description, groups?: string[], inputSchema?: zodShape, handler(args, ctx) }] }
// `groups` (default: [pluginName] if omitted) is the group-toggle tag config.mjs's
// disabledGroups/enabledTools/disabledTools filter on -- a tool can belong to more than one, e.g.
// a local-only device-specific tool might tag itself ["network", "some-device-name"] so it's
// covered by both a broad "turn off all network tools" and a narrow "turn off just that device".
// Built-ins live in ../plugins/, private ones in the configured localPluginDir (default
// <repo>/local/mcp-plugins, git-ignored). A local plugin shadows a built-in of the same name.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";

const BUILTIN_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "plugins");

export function discover(config) {
  const found = new Map();
  for (const [dir, source] of [[BUILTIN_DIR, "builtin"], [config.localPluginDir, "local"]]) {
    if (!dir || !fs.existsSync(dir)) continue;
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const entry = path.join(dir, ent.name, "index.mjs");
      if (ent.isDirectory() && fs.existsSync(entry)) found.set(ent.name, { name: ent.name, source, entry });
    }
  }
  return found;
}

export async function loadPlugin(info) {
  const mod = await import(pathToFileURL(info.entry).href);
  const def = mod.default;
  if (!def || !Array.isArray(def.tools)) throw new Error(`${info.entry}: default export needs a tools array`);
  return { ...info, description: def.description || "", tools: def.tools };
}
