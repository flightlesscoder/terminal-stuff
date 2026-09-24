# terminal-stuff MCP server

Stdio MCP server whose tools come from **plugins**. Wired into pi by `./setup/setup.sh` (module
`ai-agents`, opt-in); enable/disable plugins from the hub app's **MCP Server** tab or by editing
`mcp.enabledPlugins` in `~/.config/terminal-stuff/config.jsonc`.

```sh
node server.mjs --list-plugins     # what's discoverable, what's enabled, each plugin's tools
```

## Writing a plugin

`plugins/<name>/index.mjs` (built-in, tracked) or `local/mcp-plugins/<name>/index.mjs` (private,
git-ignored; shadows a built-in of the same name):

```js
export default {
  description: "What this collection is for.",
  tools: [{
    name: "hello",                                   // exposed as <plugin>_hello
    description: "Say hello.",
    inputSchema: (z) => ({ who: z.string() }),       // optional; zod shape
    handler: async ({ who }, ctx) => `hello ${who}`, // string or JSON-able value
  }],
};
```

`ctx` = `{ repoRoot, config, options, log }`; `options` is `mcp.pluginOptions.<plugin>` from config. Thrown
errors become MCP tool errors. See `plugins/repo` for a working example.
