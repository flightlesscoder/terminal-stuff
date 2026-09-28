# terminal-stuff MCP server

Stdio MCP server whose tools come from **plugins**. Wired into pi by `./setup/setup.sh` (module
`ai-agents`, opt-in); enable/disable plugins from the hub app's **MCP Server** tab or by editing
`mcp.enabledPlugins` in `~/.config/terminal-stuff/config.jsonc`.

```sh
node server.mjs --list-plugins     # what's discoverable, what's enabled/resolved, each plugin's tools+groups
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
    groups: ["greeting"],                            // optional; defaults to [pluginName]. See "Toggling" below.
    inputSchema: (z) => ({ who: z.string() }),       // optional; zod shape
    handler: async ({ who }, ctx) => `hello ${who}`, // string or JSON-able value
  }],
};
```

`ctx` = `{ repoRoot, config, options, log }`; `options` is `mcp.pluginOptions.<plugin>` from config. Thrown
errors become MCP tool errors. See `plugins/repo` for a working example.

**When to keep a plugin local-only instead of tracking it**: if it's wired to specific hardware you
own (a particular router's brand/model, its credentials, its quirky auth protocol) or controls a
specific remote host and its services, put it under `local/mcp-plugins/` instead of `plugins/` --
it loads exactly the same way, just invisible to git. This repo's own tracked plugins (`repo`,
`tmux`, `code`, `host`, `net`, `search`) are deliberately generic: no hardcoded device brands, IPs,
or hostnames, so they're portable to any machine. Anything host- or hardware-specific that a tracked
plugin needs (e.g. `net`'s optional gateway health checks) is read from `mcp.pluginOptions.<plugin>`
in your own untracked `config.jsonc`, never hardcoded in the plugin file itself.

## Toggling: whole plugins, groups, or one tool -- system-wide or per session

Three granularities, all in config's `mcp` section (`config/default.jsonc` documents each field):

- **Plugin**: `enabledPlugins` -- whether the collection loads at all (existing, unchanged).
- **Group**: every tool carries a `groups` array (default `[pluginName]`); `disabledGroups` turns
  off every tool tagged with any of those groups, across every enabled plugin -- e.g. one `"network"`
  group can span `net` and any local device-specific plugins, so "turn off all network tools" is one entry.
- **Individual tool**: `disabledTools`/`enabledTools` name a specific `"<plugin>_<tool>"` --
  `enabledTools` re-includes a tool whose group was turned off; `disabledTools` always wins.

That's the **system-wide default** (edit `config.jsonc`, or the hub's MCP Server tab for plugins).

**Per session**: this server runs over stdio, so a client already gets its own process per
session -- there's no separate protocol for "per-session" here, just environment the launcher sets
for that one process, layered on top of the system default (see `lib/config.mjs`'s header for the
exact precedence):

```sh
TS_MCP_PRESET=network-ops node server.mjs          # a named overlay from mcp.presets.network-ops
TS_MCP_DISABLED_GROUPS=network,remote-host node server.mjs   # ad hoc, no config edit needed
TS_MCP_ENABLED_TOOLS=net_ports node server.mjs
```

A preset is just the same three fields under `mcp.presets.<name>` in config, e.g.:

```jsonc
"presets": { "network-ops": { "disabledGroups": ["remote-host", "code"] } }
```
