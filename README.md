# terminal-stuff

My personal environment: dotfiles, setup scripts, utility scripts, tmux/nvim/Hyper plugins,
themes, cheatsheets, and a few small helper tools. The goal is to make any new machine feel
like home quickly, and to keep the differences between machines explicit.

**Target systems:** Bazzite (primary dev box), Ubuntu, macOS (Intel and ARM), and possibly
Windows 10/11 (via Git Bash or WSL).

## Quick start

```sh
git clone <this repo> ~/projects/terminal-stuff
cd ~/projects/terminal-stuff
./setup/doctor.sh          # what's installed, what's missing, how to install it
./setup/setup.sh           # interactive TUI: pick modules/steps to set up
```

## Layout

| Path             | Purpose                                                                      |
| ---------------- | ---------------------------------------------------------------------------- |
| `setup/`         | `doctor.sh` (health check) and `setup.sh` (the setup TUI, code in `setup/tui/`). |
| `dotfiles/`      | Config files that setup blocks `source` from `~/.zshrc`, `~/.tmux.conf`, etc. |
| `logs/`          | Git-ignored, size-capped logs from setup runs.                               |
| `config/`        | Layered JSONC config (`default.jsonc`, `user-template.jsonc`) -- see `config/README.md`.      |
| `apps/`          | Small standalone programs. `apps/hub` is the tabbed, mouse-enabled TUI opened from the tmux menu; `apps/mcp-server` is the pluggable MCP server (Node). |
| `local/`         | Untracked private assets (`pi-custom/` pi extensions, `mcp-plugins/`). Only the folder itself is in git. |
| `scripts/`       | Everyday utility scripts I want on my `PATH`.                                |
| `tmux-plugins/`  | Custom-developed tmux plugins.                                               |
| `nvim-plugins/`  | Custom-developed Neovim plugins.                                             |
| `hyper-plugins/` | Custom-developed Hyper.js plugins.                                           |
| `themes/`        | Color palettes and themes (WebStorm, terminal, editor, ...).                 |

More will appear as the repo grows: dotfiles/configs, cheatsheets, TUI programs, small GUI
helpers, and possibly an agent-coordinator/multiplexer.

## `setup/doctor.sh`

Read-only, OS-aware health check. It never installs anything; it reports what it finds and
prints an install hint appropriate to the detected OS/package manager for what's missing.

```sh
./setup/doctor.sh                 # full report
./setup/doctor.sh --only-missing  # just the gaps
./setup/doctor.sh --strict        # exit 1 if anything is missing (for scripting)
./setup/doctor.sh --no-color
```

Checks: zsh, tmux, ssh, fzf, oh-my-zsh, pure prompt, SCM Breeze, Hyper, tmux plugins, the hub app + its menu entry, neovim + LazyVim (+ its build deps), speech, a Nerd Font, whether
`~/.hyper.js` is set to use one, a terminal clipboard
tool (reports every one found and which the current session should use: `wl-copy`, `xclip`,
`xsel`, `pbcopy`, `clip.exe`, ...), git, curl, wget, neovim, dotnet, node, npm, a node
version manager (`n` or `nvm`), ruby, python, Spotify, Obsidian, Firefox.

GUI apps are detected wherever they may live: `PATH`, Flatpak, Snap, `/Applications`,
AppImage, or Program Files.

## `setup/setup.sh` (the setup TUI)

Python 3.8+ (stdlib `curses` only). Setup is split into **modules**, each made of independent,
individually toggleable **steps**. Steps that are already done are shown as `done ✔` and are
not pre-selected, so running it again is safe.

```sh
./setup/setup.sh                       # TUI
./setup/setup.sh --list                # modules/steps and their current state
./setup/setup.sh --run terminal-env --dry-run --yes          # scriptable; --steps a,b / --all
```

TUI keys: `↑↓` move, `space` toggle (on a module: toggle all), `a` all, `n` none,
`t` reset to "todo only", `d` dry-run on/off, `r`/`enter` run, `q` quit.

**Module `terminal-env`**: zsh, oh-my-zsh + pure prompt, fzf (with a verify step that starts
a real interactive zsh and checks Ctrl-T/Ctrl-R/Alt-C are bound to fzf),
JetBrainsMono Nerd Font (+ a verify step), Hyper, and a step that points Hyper's `fontFamily`
at the Nerd Font. Installs the **canary** build specifically: sixel image support only ever
shipped in Hyper's v4.0.0-canary.4/.5 (2023-07) -- it never reached a stable release, and the
project has had no release of any kind since, so "latest stable" is permanently stuck nine
months before that work even started. A `hyper-no-autoupdate` step sets
`disableAutoUpdates: true` in `~/.hyper.js` so it can't silently self-update to a newer *stable*
release and lose sixel.

**Module `tmux`**: tmux, [tpm](https://github.com/tmux-plugins/tpm) with `tmux-sensible`,
[`2kabhishek/tmux2k`](https://github.com/2kabhishek/tmux2k) (theme `onedark`) and
[`tmux-which-key`](https://github.com/alexwforsythe/tmux-which-key) (`prefix + Space`, needs python3),
and the config in `dotfiles/tmux/tmux.conf`: mouse on with a `prefix + m` toggle,
`default-terminal tmux-256color`, `terminal-overrides ',xterm-256color:RGB'`, an OS-aware
copy-to-clipboard on mouse drag (macOS `pbcopy`, Wayland `wl-copy`, X11 `xclip`/`xsel`, WSL `clip.exe`),
and a Shift+right-click pane menu, plus sixel image passthrough (`allow-passthrough on` +
`terminal-features sixel`) for programs like `chafa`/`img2sixel` -- needs tmux built with
`--enable-sixel` (Homebrew's is; distro packages vary) **and** a sixel-capable terminal (Hyper's
canary build below; not kitty, see its module). Needs tmux >= 3.2. The `tmux-config` step **backs up an existing
`~/.tmux.conf` to `~/.tmux.conf.bak-<YYYYmmdd-HHMMSS>` and replaces it** with a tiny managed file that
sources the repo config; put private/machine-specific tweaks in `~/.tmux.local.conf` (untracked, optional).
The verify step boots a throwaway tmux server (private socket, so a tmux you're running is never
touched) and checks each setting and binding.

**Module `hub`**: builds `apps/hub` and adds a **Terminal Stuff Hub** entry (`prefix + Space`, then `h`)
to the tmux-which-key menu; it opens the app in a tmux window (pressing it again just switches back
to that window). See `apps/hub/README.md`. The menu entry is a marked block appended to which-key's
own `config.yaml` (which is gitignored by the plugin, so plugin updates keep it). Needs the tmux
module first, plus a .NET 10 SDK to build. The build step shows `todo` again whenever HEAD or the
app's sources have moved on since the last build.

**Module `neovim`**: a recent-enough neovim (>= 0.11.2; upstream's own prebuilt tarball into
`~/.local/share/terminal-stuff/tools` on Linux when the distro package is too old, since apt in
particular often is — no sudo needed either way), ripgrep, fd (symlinked from `fdfind` on
Debian/Ubuntu), a C compiler, tree-sitter-cli (upstream's release zip; nvim-treesitter now
requires the real CLI, not npm's package), and the
[LazyVim](https://lazyvim.org) starter config with its plugins synced. **Why LazyVim, not
AstroNvim:** both have a much bigger community than AstroNvim (14.4k★/943 forks), but of the two
that do, LazyVim (27.5k★/1.8k forks, everything pushed within the last 2 weeks) is the safer pick
over NvChad (28.5k★/2.2k forks) because NvChad's actual install repo hadn't been pushed in 14
months as of this writing. The `lazyvim-config` step **backs up an existing `~/.config/nvim`
(required) and `~/.local/share/nvim`, `~/.local/state/nvim`, `~/.cache/nvim` (recommended)** to
`<dir>.bak-<date-time>` before cloning the starter, exactly as LazyVim's own install instructions
say, and removes the clone's `.git` (also per those instructions) so you can track it yourself
later. `lazyvim-plugins` does the actual (network-heavy) headless plugin sync/install.

**Module `config`**: creates `~/.config/terminal-stuff/config.jsonc` from `config/user-template.jsonc`
the first time nothing exists yet, and verifies the layered config (`config/README.md`) resolves
cleanly from wherever it's run. Never overwrites an existing file.

**Module `extras`**: lazygit, [lazydocker](https://github.com/jesseduffield/lazydocker),
[bottom](https://github.com/ClementTsang/bottom) (`btm`), [gdu](https://github.com/dundee/gdu)
(windirstat-style interactive disk usage -- drill into directories, delete inline, mouse-clickable;
picked over ncdu/diskonaut/broot, see the CLAUDE.md note if you want the comparison later),
[zoxide](https://github.com/ajeetdsouza/zoxide), jq, and Spotify. Like neovim/tree-sitter-cli,
lazygit/lazydocker/bottom/gdu install from upstream's own release tarball on Linux rather than
apt/dnf (none of the four have an apt/dnf package); zoxide and jq are reliably packaged everywhere,
so those use apt/dnf/brew directly. zoxide's shell integration (`eval "$(zoxide init zsh)"`) isn't
wired into the zsh module yet -- this step only installs the binary.

**Module `speech`**: deploys `dotfiles/scripts/speak-background.sh` to `~/apps/scripts/speak-background.sh`
(never overwrites an existing one) and verifies it's executable, syntactically valid, and that a
speech engine is available. See `apps/hub`'s Speech tab below for configuring it.

**Module `ai-agents`** (opt-in -- every step defaults off, so a bare run selects nothing): installs the
[pi coding agent](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) and your pi packages
(`pi-web-access`, `pi-fff`, `pi-goal-x`, `pi-vcc`, `pi-mcp-adapter`, `pi-time-sense`), symlinks private pi
extensions from `local/pi-custom/*.ts` into `~/.pi/agent/extensions/`, installs `apps/mcp-server`'s
dependencies, and registers that server in pi's `~/.pi/agent/mcp.json`. `doctor.sh` reports the same.

Verify steps are read-only and show `done ✔` once they pass (or why not).

**Module `kitty`** (optional -- both steps default off in the TUI, only run if selected): install
and configure [kitty](https://sw.kovidgoyal.net/kitty/) as a trial terminal alongside Hyper, the
first candidate for a longer-term replacement. Does **not** support sixel and never will --
kitty deliberately implements only its own (more capable) graphics protocol instead, on by
default with no config needed.

**Module `lazyvim-dev`** (needs the `neovim` module's LazyVim install first): language tooling for
React/TypeScript/modern JS, C#, PowerShell, Python, Bash and SQL. Enables LazyVim's official
`lang.typescript`/`json`/`python`/`dotnet`/`sql` extras by editing `~/.config/nvim/lazyvim.json`
directly (same file `:LazyExtras` writes -- works headlessly); installs node + PowerShell
(`pwsh`) as the runtimes those LSPs need; and, since **Bash and PowerShell have no official
LazyVim extra** (checked the actual extras listing, not guessed), deploys a small custom plugin
spec (`dotfiles/nvim/extra-langs.lua`) wiring up `bashls`/`powershell_es` the same way LazyVim's
own extras do. `lang.sql` already bundles vim-dadbod + vim-dadbod-ui -- confirmed by watching it
install -- so that's the database answer for MSSQL/Postgres/Mongo/Azure SQL; a
`lazyvim-dadbod` step adds a connections template (`~/.config/nvim/lua/plugins/dadbod-connections.lua`,
outside this repo, safe for real credentials) with commented example URLs for each. For merge
conflicts, lazygit's own inline resolver (already installed by `extras`) is the answer; nothing
extra to set up there.

## Config (`config/`)

JSON with `//`/`/* */` comments, layered: `config/default.jsonc` (tracked) →
`~/.config/terminal-stuff/config.jsonc` (yours; `./setup/setup.sh` creates it) →
`./.terminal-stuff.jsonc` (optional, per-directory). Objects merge key by key; arrays concatenate
(so your config *extends* the default's, e.g. its `paths` list) unless a value is wrapped as
`{"$replace": [...]}`, which replaces it outright -- used for things like tmux status segments,
where order+membership together are the point. See `config/README.md`. Parsed identically by
`setup/tui/jsonc.py` and `apps/hub/Jsonc.cs`.

## `apps/hub` tabs

- **Settings > Paths**: paths relevant to this setup, each with a live ✔/✘ for whether it exists
  on disk. Extend the list from your own config (`paths` in `config/README.md`); more Settings
  sections can be added alongside Paths later.
- **Status Segments**: configure, reorder and toggle tmux2k's status bar segments (three lists --
  Left / Right / Off -- with Move/Up/Down/Save/Revert). Save writes to
  `~/.config/terminal-stuff/config.jsonc` and, if you're inside tmux, applies it live via
  `tmux set-option` so you see the result immediately; it persists the next time tmux starts too.
- **Speech**: create/configure/mute `~/apps/scripts/speak-background.sh` -- a background
  text-to-speech script other utilities can call (`speak-background.sh some text` speaks "some
  text"; it never blocks the caller). macOS uses `say` (enhanced voices: pass the exact voice name
  from `say -v ?`, e.g. `-v "Samantha (Enhanced)"`); Linux tries spd-say, espeak-ng, festival, then
  flite (whichever is installed); Windows/WSL shells out to PowerShell's `System.Speech`. Edit each
  engine's command-line arguments (shell-like quoting: `-v "Samantha (Enhanced)" -r 175`), toggle
  Mute (comments out the one line that actually speaks -- a harmless no-op, everything else still
  runs), and Test right from the tab.
- **MCP Server**: see every plugin `apps/mcp-server` can load (built-in and private), toggle which are
  enabled, and see whether pi is wired to it. Save writes `mcp.enabledPlugins` to your config; restart pi.
- **Setup**: the same information `./setup/doctor.sh` reports (every module, every step, its
  current state), with the option to actually run any of it -- modules on the left, that module's
  steps on the right, a Dry Run checkbox, and Run Step / Run All Todo In Module, streaming live
  output and refreshing state when done. A UI on top of `setup/setup.sh --list/--run --json`
  (new flag -- machine-readable JSON output, alongside the normal human-readable one); it never
  reimplements install logic in C#, Python stays the one place that lives.

How it changes your files:
- Edits to `~/.zshrc` / `~/.tmux.conf` are **marked blocks** (`# >>> terminal-stuff:NAME >>>`)
  that source a file from `dotfiles/`; everything outside the blocks is left alone, and the
  file is backed up (`*.bak-terminal-stuff-<time>`) before the first change in a run.
- `~/.hyper.js` is only created if it doesn't exist; the `hyper-font` step later edits just its
  `fontFamily` line (backed up first) and Hyper live-reloads the change.
- Dry-run logs every command/write without executing it.
- On Bazzite packages come from Homebrew; Hyper is installed as an AppImage in `~/Applications`.
- `config-init` only ever creates `~/.config/terminal-stuff/config.jsonc`; it never touches `config/default.jsonc`.
- Not done for you: making zsh your login shell (`chsh`).

**Logs:** every run writes a verbose log to `logs/setup-<time>-<pid>.log` (environment, tool
versions, each command with exit code and full output, file diffs, tracebacks);
`logs/latest.log` points at the newest. `logs/` is git-ignored and capped at 25 MB / 50 files
(oldest deleted first; one run rotates at 5 MB). **Attach the log when something goes wrong.**

## Conventions

- **Portable shell.** Scripts use `#!/usr/bin/env bash` and stay compatible with bash 3.2
  (the macOS default). No GNU-only flags without a fallback.
- **Idempotent setup.** Anything in `setup/` must be safe to run twice, and should back up
  rather than overwrite existing files.
- **OS-aware, not OS-specific.** Detect the OS/distro and branch; don't fork whole scripts
  per platform unless it's truly necessary.
- **Bazzite is immutable.** Prefer Homebrew, Flatpak, or distrobox over `rpm-ostree` layering.

## Private overrides

This repo is public and is used at both home and work, so anything private stays out of it.
The `.gitignore` excludes `*.local`, `*.private`, `.private/`, `local/`, `secrets/` and `.env*`.
Tracked configs should *source* an optional local file rather than embed private values, e.g.:

```sh
[ -f ~/.zshrc.local ] && . ~/.zshrc.local
```

Never commit tokens, work hostnames, or employer-specific configuration.
