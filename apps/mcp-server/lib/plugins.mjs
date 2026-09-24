// Plugin discovery/loading. A plugin is a directory holding index.mjs whose default export is
//   { name?, description, tools: [{ name, description, inputSchema?: zodShape, handler(args, ctx) }] }
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
