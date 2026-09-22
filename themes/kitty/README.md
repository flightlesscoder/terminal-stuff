# Kitty themes

Each subdirectory is one selectable kitty theme:

- `theme.json` -- `{"name": ..., "description": ...}`, shown by the hub app's kitty theme picker.
- `kitty.conf` -- colors + tab bar settings only (no `font_family`/`font_size`; those are set once
  by the tracked `dotfiles/kitty/kitty.conf` template, not per theme). Spliced into
  `~/.kitty.local.conf` as a managed block (marker `kitty-theme`), which the deployed
  `~/.config/kitty/kitty.conf` already `include`s.
- `tab_bar.py` (optional) -- only present when the theme sets `tab_bar_style custom`. Deployed
  verbatim to `~/.config/kitty/tab_bar.py`, since kitty only ever looks for that file in its own
  config directory, never relative to whatever file included the theme.

Applying a theme is "apply one theme's files"; there's no partial-merge between themes.

## Where this is implemented

Two independent implementations, same as `setup/tui/jsonc.py` <-> `apps/hub/Jsonc.cs` -- change
one, change the other:

- `setup/tui/modules/kitty.py`'s `kitty-theme` step: applies `DEFAULT_KITTY_THEME` (currently
  `synthwave-kat`) non-interactively, for a fresh machine setup.
- `apps/hub`'s Kitty Theme tab: lists every theme here (reads `theme.json`) and lets you switch
  live.

## Current default

**Synthwave Kat** -- see its `theme.json` for why. Its tab shape (`tab_powerline_style angled`)
was matched against tmux2k's *actual* separator glyph (read the live status bar's raw bytes:
U+E0B2, confirmed real -- not assumed from memory), not guessed.
