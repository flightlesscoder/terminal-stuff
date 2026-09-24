# local/

Untracked, machine-specific assets. Git keeps this directory (`.gitkeep`, this file) but ignores
everything else in it -- see `.gitignore`. Nothing here is ever pushed.

- `pi-custom/*.ts` -- your own pi extensions (custom model providers/adapters). The `ai-agents`
  setup module symlinks each one into `~/.pi/agent/extensions/`.
- `mcp-plugins/<name>/index.mjs` -- private plugins for the terminal-stuff MCP server
  (`apps/mcp-server`). Enable one by adding its name to `mcp.enabledPlugins` in your config.
