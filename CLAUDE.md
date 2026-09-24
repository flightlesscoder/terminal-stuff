# CLAUDE.md

Personal dotfiles / environment repo (public on GitHub, used at home and at work). See
`README.md` for the user-facing overview and layout.

## Target environments

Bazzite (Fedora Atomic, immutable; primary), Ubuntu, macOS Intel + ARM, possibly Windows
10/11 via Git Bash/WSL. Every script must behave sensibly on all of them, or fail with a
clear message on the ones it doesn't support.

## Layout

- `setup/` — `doctor.sh` (read-only health check) and `setup.sh` → Python curses TUI in `setup/tui/`
- `dotfiles/` — files that managed blocks in `~/.zshrc` / `~/.tmux.conf` source; `logs/` — git-ignored run logs
- `apps/` — standalone programs; `apps/hub` = C#/.NET 10 + Terminal.Gui 2.5 tabbed TUI (build output in git-ignored `bin/`, `obj/`)
- `scripts/` — day-to-day utility scripts
- `tmux-plugins/`, `nvim-plugins/`, `hyper-plugins/` — custom-developed plugins
- `themes/` — palettes and editor/terminal themes
- Planned: dotfiles/configs, cheatsheets, TUI programs, small GUI helpers, maybe an agent multiplexer

## Conventions

- Shell scripts: `#!/usr/bin/env bash`, **bash 3.2 compatible** (macOS): no associative
  arrays, `${var,,}`, `mapfile`, or GNU-only flags (`sed -i` without a suffix, `readlink -f`,
  `date -d`) unless guarded. Use `set -u`; quote everything.
- Detect OS via `uname -s` and `/etc/os-release` (`ID`); see `setup/doctor.sh` for the pattern.
- Setup scripts must be idempotent and back up existing files instead of overwriting.
- `doctor.sh` is read-only. Never make it install or change anything.
- On Bazzite, don't suggest `rpm-ostree install`; prefer Homebrew, Flatpak, distrobox. Note
  `/usr` is read-only and `$HOME` is really `/var/home/<user>`.
- Match existing style and comment density; keep scripts small and single-purpose.

## Setup TUI (`setup/tui/`)

Python 3.8+ stdlib only (no pip deps; keep `from __future__ import annotations`, no `match`).
- `core.py`: `Step` (id, title, description, `check`, `run`, `needs_sudo`, `supported`), `Module`,
  `Ctx`. **Every mutation must go through `Ctx`** (`run`, `write_text`, `ensure_block`, `mkdir`,
  `download`, `git_clone`, `install_pkg`) so `--dry-run` and logging stay trustworthy. `check`
  must be read-only. "Verify" steps should use their read-only probe *as* the `check` so they can show `done`
  (never a check that is always "todo"). Raise `StepError` with an actionable message for expected failures.
- Add a module: create `modules/<name>.py` with `build() -> Module`, register in `modules/__init__.py`.
- Config edits use `ctx.ensure_block(path, name, body)` (idempotent marked blocks), never blind appends.
- Logging is verbose by design (`logsetup.py`); log new decisions/commands at INFO/DEBUG. Logs live
  in `logs/`, are capped (25 MB/50 files) and git-ignored. When debugging a user report, read `logs/latest.log` first.
- **Anything that starts tmux must use `private_server()`** (`modules/tmux.py`): the process may itself be
  running inside tmux, and an inherited `TMUX`/`TMUX_PLUGIN_MANAGER_PATH` (or the default socket) makes tpm
  install into, or load from, the *real* `~/.tmux/plugins` even when `HOME` is a scratch dir. Verify after a
  sandboxed test that the real `~/.tmux`, `~/.zshrc`, etc. are untouched.
- Test without touching the real system: `HOME=<scratch dir> ./setup/setup.sh --run MODULE --steps ... --yes`
  (add `--dry-run` first). Drive the curses UI with a detached tmux session + `send-keys`/`capture-pane`.

## Apps (`apps/`)

- `apps/hub`: `hub.csproj` stamps build time + git short hash into the binary at build (`StampBuildInfo` target →
  `obj/.../BuildInfo.g.cs`; "none" when the repo has no commits, `dirty` = uncommitted changes). `hub --about`
  prints the stamp (used by the setup module's checks). Add tabs as `View`s with a `Title` inside a
  `Tabs` (Terminal.Gui **2.5** API: `Application.Create().Init()`, `Tabs`, `Runnable/Window`; it differs from v1 and from
  most online examples, so read the package XML docs in `~/.nuget/packages/terminal.gui/2.5.0/lib/net10.0/`).
- `apps/hub/hub` is the launcher (used by the tmux menu); it pauses with a message on failure so a tmux window doesn't vanish.
- Test TUIs in a real pty (detached tmux + `capture-pane`); mouse can be simulated by sending SGR sequences
  (`\e[<0;X;YM` then `\e[<0;X;Ym`) with `send-keys -l`.
- The tmux menu entry is a marked block in which-key's `config.yaml` (needs `items:` to be the last top-level key).

## GitHub-release-based tool installs (`modules/neovim.py`, others to follow the same shape)

When a distro package is unreliable (too old, wrong binary name, or plain absent — apt's neovim,
any distro's tree-sitter-cli), install upstream's own release asset instead of fighting the
package manager: `ctx.fetch_json` the `.../releases/latest` API, pick the asset by `osinfo.arch`/
`os`, `ctx.download` it, `ctx.extract_archive` (strips a shared top-level dir automatically; set
`strip_common_dir=False` for an archive whose members are already flat), `ctx.symlink` the binary
into `~/.local/bin`. No sudo needed. **`ctx.symlink` re-adds its own parent dir to `PATH` for the
rest of this process** — `osinfo.augment_path()` only scans for existing directories once at
startup, so a `~/.local/bin` a step just created wouldn't otherwise be seen by a `ctx.which()`
later in the same run.

## Config (JSONC): `setup/tui/jsonc.py` <-> `apps/hub/Jsonc.cs`

Two independent implementations of the same contract (config/README.md: search order, deep-merge,
`${TOKEN}` substitution, `{"$replace": [...]}`) -- **change one, change the other**, and keep their
test cases in lockstep (Python's are inline asserts you can run ad hoc; the C# ones were verified
by copying Jsonc.cs into a scratch project and running assertions there -- there's no permanent
test project yet). `set_replace_field`/`SetReplaceField` is targeted text surgery on one JSON
key's value (mirrors `Ctx.ensure_block`'s philosophy for shell configs): a strip-comments-then-
rewrite round trip would destroy every comment in the user's file, so it finds and replaces only
the requested key's value span, byte range, leaving everything else untouched.

## Hub app UI conventions (`apps/hub/*.cs`)

- New tab: build a `View` with `Title` set (that's the tab label) and `tabs.Add(...)` it in
  `Program.cs`. A tab whose data can fail to load (e.g. an invalid config) should catch and show
  `ErrorTab.Create(title, message)` instead of throwing -- one bad file shouldn't crash hub.
- Multi-section tab (see `SettingsTab.cs`): a sections `ListView` on the left, a content `View` on
  the right rebuilt from `(string Name, Func<View> Build)[]` on selection change. Add a section by
  adding one array entry.
- **`ListView.SelectedItem`/`Value` reads back null once the list no longer has focus.** A
  `Button.Accepting` handler runs *after* focus has already moved to the button, so reading
  `someListView.SelectedItem` from inside it is always too late. Capture `(list, index)` at
  interaction time instead, from `ValueChanged` (covers keyboard nav and a click that lands on a
  new row) plus a `MouseEvent` fallback (covers a click on the row that was already selected, so
  `ValueChanged` wouldn't otherwise fire) -- see `StatusSegmentsTab.cs`'s `Track()`/`active`.
- Test interactively with a real pty (detached tmux + `send-keys -l` with SGR mouse escapes +
  `capture-pane`), same as the setup TUI. Get click coordinates from an actual fresh
  `capture-pane` of the running app, not from a previous run or from computed layout math --
  content shifts between renders and stale coordinates silently click the wrong pane. A
  live on-screen debug label (temporary or, as with `StatusSegmentsTab`'s selection readout,
  genuinely useful to keep) beats inferring state from side effects when a click doesn't do what
  you expect.

## `apps/hub` Speech tab <-> `dotfiles/scripts/speak-background.sh`

`SpeechScript.cs` edits the deployed script's `NAME=(...)` bash-array-literal lines (one per
engine's args) and the SPEAK-LINE mute toggle, in place, leaving the rest of the file untouched --
same "surgical edit, not a rewrite" philosophy as Jsonc.cs. **The array span must be found by
depth+quote-aware scanning, not a greedy/lazy regex**: a value can itself contain a paren (a macOS
enhanced voice name like "Samantha (Enhanced)" is the whole reason args are bash arrays and not
plain strings here), and the template's own inline example comments (`# e.g.: SAY_ARGS=(...)`)
have unrelated parens on the same line -- a regex matching `\(.*\)` greedily over-matches into the
comment, and matching `\(.*?\)` lazily under-matches at the first paren inside a real quoted
value. `FindArraySpan` walks the text like Jsonc.cs's `ScanValueSpan` does for JSON.

If you add a new engine, add it to: the script's OPTIONS block + `_speak_now()` + `detect_engine()`
(`dotfiles/scripts/speak-background.sh`), `ArgFields`/`DetectEngine` (`SpeechScript.cs`), and
`ENGINE_ORDER`/`detect_engine` (`setup/tui/modules/speech.py`) -- three places, kept in sync by hand.

## Disk-usage tool choice (`extras.py`'s gdu-install)

Picked **gdu** over ncdu (safer/more universal but single-threaded, keyboard-only, no apt/dnf
package situation doesn't apply -- it IS packaged everywhere, just slower), diskonaut (closest
visual match to WinDirStat's treemap, but unmaintained since 2024-03: same red flag as NvChad's
starter earlier), and broot (great, 13k stars, but a general tree navigator first --
disk-usage/"whale-spotting" is a secondary mode, not its core purpose). Revisit if gdu's own
upkeep ever stalls the way diskonaut's did.

## LazyVim state files (`lazyvim_dev.py`)

`~/.config/nvim/lazyvim.json`'s `extras` array holds **fully-qualified** module paths
(`"lazyvim.plugins.extras.lang.dotnet"`), not short names -- verified by hitting the opposite
assumption for real: writing the file with no `version` key makes LazyVim's own migration path
(`lua/lazyvim/util/json.lua`, the `not json.data.version` branch) treat it as the pre-v1 format
and PREPEND that same prefix again, silently breaking every extra with a doubled module path.
Always write `version` (current: `LAZYVIM_JSON_VERSION` in lazyvim_dev.py) alongside `extras`.

`+MasonToolsInstallSync` does not actually block under `nvim --headless` (~0.03s return, then
mason logs an abort for whatever was still mid-download) -- pump the event loop yourself instead:
`+MasonToolsInstall` followed by `-c "lua vim.wait(45000, function() return false end, 500)"`.
Also run `+Lazy! sync` as its own separate `nvim --headless ... +qa` invocation, not combined with
a mason install in the same process -- a newly-installed extra's `opts()` (which is what feeds
mason-tool-installer's `ensure_installed`, e.g. lang.sql's own `sqlfluff`) isn't reliably merged
yet in the same process that just ran the sync.

## Background work in hub (`SetupTab.cs`'s Task.Run + app.Invoke)

**The static `Application.Invoke(Action)` does not reliably marshal work back to the UI thread in
2.5.0 -- use the `IApplication` instance's `Invoke` instead** (`app.Invoke(...)`, threading `app`
from `Program.cs` into the tab, e.g. `SetupTab.Create(repoRoot, app)`). Hit this for real: a
background `Task.Run` called `Application.Invoke(() => status.Text = "...")` after a subprocess
finished, and the label update was silently never applied -- no exception, no error, the
subprocess had genuinely completed (its output file existed, its log existed) but the screen
stayed frozen on "running..." indefinitely. Bisected by adding an `Application.Invoke` right at
the top of the `Task.Run` lambda (also never appeared) and confirming a new thread-pool thread
really was spawned; swapping every call in the tab from `Application.Invoke` to `app.Invoke` fixed
it immediately, no other change needed. The compiler's own obsolete-warning on the static overload
("The legacy static Application object is going away") is the standing hint this exists.

Pattern for any tab that shells out to something slow: run the process on `Task.Run`, marshal
every UI mutation (including ones inside a per-line callback like `SetupModel.Run`'s `onEvent`)
through `app.Invoke(...)`, and support cancellation via a `CancellationTokenSource` the Cancel
button can trigger, killing the process tree (`proc.Kill(entireProcessTree: true)`) -- verified
this leaves no orphaned children (checked `ps` after a mid-run cancel of a step that itself spawns
`nvim --headless` grandchildren).

## Testing hygiene: kill every tmux test server, every time

**A single test session left running as background "cleanup for later" compounds fast.** Hit this
for real: repeated hub UI tests each used a fresh `tmux -L <name>` socket (to dodge stale-content
coordinate issues), and stray `dotnet hub.dll` processes plus their tmux servers accumulated
across many turns of the same session -- discovered only by accident (`ps` for an unrelated
reason) showing multiple `hub.dll` trees alive for 11+ hours. A later overly-broad cleanup attempt
then killed this session's own process tree. Going forward: kill each test's tmux server
(`tmux -L <name> kill-server`) and verify via `ps` immediately after that test's assertions are
done, before starting the next one -- don't defer cleanup, and never `kill`/`pkill` by a broad
pattern without confirming the target PID's own identity (cmdline, parent) first.

## kitty.conf's local-override include (`dotfiles/kitty/kitty.conf`)

Use `include ${HOME}/...`, not `globinclude ~/...`, for an optional personal-overrides file.
`globinclude` is specifically for **glob patterns relative to this config file's own directory**
and rejects home/absolute paths outright ("non-relative patterns are unsupported" -- kitty's exact
error, hit for real by the user after this shipped with `globinclude ~/.kitty.local.conf`); `include`
is the one for a single literal file, is documented to expand environment variables, and is silently
a no-op if the target doesn't exist. Prefer `${HOME}` over `~` there since only the former is
confirmed by kitty's own docs.

**Also re-learned the testing-hygiene lesson the hard way, this time with kitty:** a killed/timed-out
`kitty` launch can leave `kitten __watch_conf__`/`kitten __atexit__` helper processes running even
after the main process is gone -- `timeout`'s SIGTERM to its direct child isn't enough. Verify with
`ps | grep kitt` after every test launch, not just after the `kitty` process itself looks gone.

## tmux2k status segments must be re-applied on every tmux start, not just live (`apply-status-segments.sh`)

The hub app's Status Segments tab (`StatusSegmentsTab.cs`) writes `tmux.statusLeft`/`statusRight`
into `config.jsonc` AND, if it's running inside a live tmux session, applies them immediately via
`tmux set-option -g @tmux2k-left-plugins/-right-plugins`. **That live apply only patches the
currently-running server's in-memory state.** Nothing else ever read `config.jsonc` back into
tmux, so `tmux kill-server` + restart (or a machine reboot) re-sourced `dotfiles/tmux/tmux.conf`
from scratch, which never set those options at all -- tmux2k silently fell back to its own
built-in plugin list (which includes `cpu`), even though `config.jsonc` on disk was correct and
the hub tab showed the right thing. Hit for real: user removed `cpu` from Right via the hub,
restarted tmux, and it came back.

Fix: `dotfiles/tmux/tmux.conf` now has its own `run-shell` line (before tpm's `run` line, so it's
set before tmux2k reads it) that calls `dotfiles/tmux/apply-status-segments.sh`, which shells out
to `python3 -m tui.jsonc_cli tmux-segments` (new subcommand -- prints `TS_LEFT=`/`TS_RIGHT=` lines,
`jsonc.resolve()`'d the same way the hub and doctor.sh do) and `tmux set-option`s the result. The
script needs the repo root to find `setup/tui/`, so the managed block in `~/.tmux.conf` (`tmux.py`'s
`block_body()`) now sets `@terminal-stuff-repo` immediately before `source-file`ing the tracked
config -- **if you change `block_body()`'s shape, re-run the `tmux-config` step for real** (it's
`ensure_block`, idempotent, but only picks up the new line once actually re-run). Best-effort:
any failure (python3 missing, no config.jsonc yet) is silently skipped so startup never breaks and
tmux2k just uses its own defaults.

**Testing gotcha hit while verifying this:** `tmux <subcommand> -f <file>` silently does NOT load
that config -- `new-session` (and most subcommands) don't have a `-f` flag at all, but tmux doesn't
error on the typo either, it just starts with zero custom config and every `set -g` you expected
silently never happened. `-f` is a **global** flag and must come before the subcommand:
`tmux -f <file> new-session -d -s x`, not `tmux new-session -d -s x -f <file>` (matches
`tmux.py`'s own `tmux_probe()`, which already had this right).

**Also hit for real while testing:** `apply-status-segments.sh`'s internal `tmux set-option` calls
have no `-L <name>` of their own -- they go wherever `$TMUX`/`$TMUX_TMPDIR` point, same as any
plain `tmux` invocation. A test that starts an isolated session with `tmux -L some-name ...` but
then runs the script bare (no matching env) does NOT reach that isolated session -- it silently
falls through to the **default socket**, which may be a real, attached, user-visible tmux server.
This happened here: two separate premature test runs of the script (before its env was corrected)
landed on the real default-socket session instead of the intended sandbox. Both were harmless by
luck (the values being set happened to already match what was live), but it could just as easily
not have been -- always isolate with `TMUX_TMPDIR` (matching `modules/tmux.py`'s own
`private_server()` pattern, which the setup module gets right and my ad hoc shell testing initially
didn't) for *any* command that might shell out to bare `tmux`, not just for the `tmux -L`/`-f`
invocation that starts the sandboxed server itself -- a `-L` name alone doesn't protect a
subprocess three levels down that never sees that flag.

## Node.js version management (`node` module) + `scm_breeze`/shell extras (`terminal_env.py`)

**`node` module**: installs tj/n by downloading `bin/n` straight from GitHub (`raw.githubusercontent.com/tj/n/master/bin/n`) into `$N_PREFIX/bin/n` and `chmod 755`-ing it --
deliberately *not* via npm (circular: n's whole job is bootstrapping node before npm exists) or
the third-party `n-install` (mklement0/n-install; it modifies shell rc files itself, outside our
marker system -- same reason we skip scm_breeze's own installer, below). n has no Windows support
at all, not even Git Bash (confirmed against its own README) -- `node-nvm-windows-install`
installs `coreybutler/nvm-windows` via winget (`CoreyButler.NVMforWindows`) as the fallback there.
Both `N_PREFIX` ($HOME/apps/n-prefix) and `NPM_CONFIG_PREFIX` ($HOME/apps/npm-prefix) are put on
PATH **along with their bare (non-`/bin`) directories** (`dotfiles/zsh/node.zsh`) -- n's own docs
only call for `$N_PREFIX/bin`, but the user explicitly asked for all four; it's harmless (n never
puts anything directly in `$N_PREFIX` itself, so those entries just sit unused on PATH), so don't
"simplify" this back down to two dirs without checking first.

**`scm_breeze`** (git shortcuts/keybindings, `terminal_env.py`'s `scm-breeze-*` steps): scm_breeze
has no built-in "disable everything" env var (checked its source -- `SCM_BREEZE_DISABLE_ASSETS_MANAGEMENT`
only skips its design/repo-index assets, not the git aliases/keybindings that actually caused the
problem). We don't run its own `install.sh` either: it unconditionally appends an unwrapped,
unguarded `source .../scm_breeze.sh` line to `~/.zshrc` via plain `>>`, outside our marker system --
that would both duplicate our managed block and defeat the guard below. Instead: `scm-breeze-install`
just clones `scmbreeze/scm_breeze` (the org repo; `ndbroadbent/scm_breeze` is the old/original,
now effectively a fork), `scm-breeze-config` replicates only the part of `install.sh` we actually
need (copying `~/.scmbrc`/`~/.git.scmbrc` from its `*.example` templates, matching its own
`_create_or_patch_scmbrc`, but never overwriting existing ones), and `scm-breeze-zshrc` wraps the
source line itself in `dotfiles/zsh/scm_breeze.zsh` with `[ -z "${CLAUDECODE:-}" ]`. Hit for real:
the user's stated reason ("scmb wrapper can conflict with claude") and their literal condition
(`-z $CLAUDECODE`, i.e. opt out when CLAUDECODE is *unset*) contradicted each other -- asked, and
confirmed the intent is the reverse of what was literally said: load scm_breeze normally in
regular terminal sessions, skip it only when Claude Code is active (its git wrapper errors --
something in its safe-eval helpers -- when Claude shells out to git). Always flag a stated
condition that contradicts its own stated reason rather than implementing either half silently.

**`zsh_block`/`ZSHRC`** (the "(check, run) pair for a managed ~/.zshrc block that sources
dotfiles/zsh/X" helper) moved from `terminal_env.py` into `_common.py` so `node.py` could reuse it
too -- if you add a third module that needs a zshrc block, it's already shared.

## tmux windows defaulted to bash even though kitty defaults to zsh (`set-default-shell.sh`)

Root cause: tmux's `default-shell` option, when not explicitly set, falls back to `$SHELL` / the
passwd-database login shell -- and the user's actual account shell had never been `chsh`'d to zsh
(confirmed for real: `$SHELL` and `getent passwd $(id -un) | cut -d: -f7` were both `/bin/bash`),
even though zsh is fully set up and used interactively everywhere else. kitty never hit this
because `dotfiles/kitty/kitty.conf` hardcodes `shell __ZSH__`, substituted with `ctx.which("zsh")`
by `kitty.py`'s `config_run` -- but that's a **one-time template substitution at install time**,
which doesn't fit tmux.conf's architecture (it's `source-file`'d fresh from the repo on every
start, never copied/rendered -- see the tmux2k status-segments fix above for why baking in a
value once is the wrong shape for a file that's re-evaluated on every start).

Fix: `dotfiles/tmux/set-default-shell.sh`, called via `run-shell` from `dotfiles/tmux/tmux.conf`
(basics section, near the top) on every tmux start -- resolves zsh fresh each time (`command -v
zsh`, then a handful of common install locations) and `tmux set-option -g default-shell`s it.
Same "re-resolve on every start, not once" shape as `apply-status-segments.sh`. Best-effort: if
zsh can't be found at all, it's a silent no-op.

Deliberately did **not** also `chsh` the user's actual login shell as part of this fix, even
though that's the more "correct" underlying repair (fixes every other program that resolves the
account's shell, not just tmux) -- `chsh` requires the target shell listed in `/etc/shells`,
which isn't guaranteed for a Homebrew-installed zsh, and changes system account state outside a
dotfiles-repo script's usual blast radius. Worth a dedicated, opt-in setup step if this comes up
again, not a silent side effect of a tmux fix.

## `Ctx.run(sudo=True)` failed with "a password is required" even right after typing the password

Root cause: `Ctx.run`'s subprocess is always started with `start_new_session=True` (needed so the
timeout-kill path can safely `os.killpg` the whole child process tree without touching our own).
That detaches the child into a **brand-new session with no controlling tty at all**. sudo's cached
credential ticket (created by `cli.py`'s pre-run `sudo -v`, which runs attached to the real
terminal) is scoped to that tty/session -- a `sudo -n` inside the detached child can't find or
match it, so it fails immediately with "a password is required", even moments after a real,
successful interactive sudo prompt in the same shell. Never surfaced before because this repo's
primary dev machine (Bazzite) uses Homebrew for package installs (`pm_sudo` is only true for
apt/dnf), so no `sudo=True` step had ever actually been exercised for real here until `zsh-chsh`
(`terminal_env.py`) -- Ubuntu/dnf users hitting `pm_sudo`-gated installs would have hit this too.

Fix: `Ctx.run` now only detaches (`start_new_session=True`) for non-sudo commands; a `sudo=True`
command stays attached to our own session/tty so the ticket keeps matching, and its timeout-kill
path uses a plain `proc.kill()` instead of `killpg` (can't safely killpg a child that was never
given its own process group). Minor accepted tradeoff: a sudo command's own runaway grandchildren
on timeout won't all be swept the way a detached command's would -- fine for what `sudo=True` is
actually used for here (`chsh`, `tee >> /etc/shells`, `apt-get`/`dnf install`), none of which spawn
stray long-lived orphans the way e.g. `nvim --headless` might.

## Kitty themes (`themes/kitty/`) + the hub app's Kitty Theme tab

Each `themes/kitty/<slug>/` is one selectable theme: `theme.json` (name/description, shown by the
picker), `kitty.conf` (colors + tab bar only -- no `font_family`/`font_size`, those are set once by
the tracked `dotfiles/kitty/kitty.conf` template, not per theme), and an optional `tab_bar.py` for
a theme using `tab_bar_style custom`. Applying one means: splice `kitty.conf`'s content into
`~/.kitty.local.conf` as a managed block (marker `kitty-theme`) -- already `include`d by the
deployed kitty.conf -- and, if present, copy `tab_bar.py` verbatim to `~/.config/kitty/tab_bar.py`
(kitty only ever looks for that file in its own config dir, never relative to whatever file
included the theme, so it can't live inside the spliced block). See `themes/kitty/README.md`.

**Two independent implementations, same as `jsonc.py`/`Jsonc.cs`** -- change one, change the
other: `setup/tui/modules/kitty.py`'s `kitty-theme` step (applies `DEFAULT_KITTY_THEME` non-
interactively for a fresh machine) and `apps/hub`'s `KittyThemeTab.cs` (interactive switching).
The block-splice logic itself is shared on the C# side via the new `BlockFile.cs` (`EnsureBlock`/
`ReadBlock`), a straight port of `Ctx.ensure_block`/`block_current`/`_splice`'s marker convention
(`# >>> terminal-stuff:NAME >>>` ... `<<<`) -- there wasn't a marked-block editor on the Hub side
before this (Jsonc.cs and SpeechScript.cs both do *targeted* text surgery on a different shape of
file, not this "whole block" pattern), so this is a new small shared primitive, not a one-off.

**Real bug hit building `KittyThemeTab.cs`'s Apply button**: after `Apply()` succeeds, refreshing
the theme list's `ObservableCollection` (`.Clear()` + re-`.Add()` each label, so the new "applied"
marker shows) fires the list's own `ValueChanged` -- which re-enters the same `Capture()` closure
used for normal user selection and resets the tracked `selected` index to whatever the refresh
lands on, *after* `Apply()` already ran correctly with the right value. Symptom: the status line
and the list's `*` marker both showed the correct newly-applied theme, but the detail pane right
next to it reverted to showing the *previous* selection's description -- because `ShowDetail(selected)`,
called after the refresh, was reading the clobbered value. Same root shape as `StatusSegmentsTab.cs`'s
documented `ListView.SelectedItem`-goes-null-after-focus-loss gotcha, but from a different trigger
(refreshing the bound collection, not losing focus) -- catch: **snapshot the index you need
*before* any call that might touch the list's own state, don't re-read a tracking variable that a
side effect of your own code could have just changed.** Fixed by capturing `var i = selected;`
before `Apply()`/`RefreshLabels()`, then using `i` throughout and re-asserting `selected = i`
afterward (plus `list.SetSelection(i, false)` to keep the visual cursor in place too).

**Synthwave Kat's tab shape wasn't guessed**: matching tmux2k's own separator meant reading the
*actual bytes* of the live status bar (`tmux show-option -gv status-right` piped through a Python
one-liner checking `ord(ch) > 0x2000`), not assuming from memory -- came back U+E0B2, the classic
powerline hard-arrow (mirrored for right-alignment), confirming kitty's `tab_powerline_style angled`
(not `slanted`, which the original Neon Synthwave theme used) was the actual match.

## kitty's own shell integration was quietly overriding `cursor_shape` at the prompt

Wanted: a solid filled cursor block while a kitty window has keyboard focus, a hollow outline
while it doesn't -- matching tmux's own active/inactive-pane cursor behavior (`dotfiles/kitty/kitty.conf`
now pins `cursor_shape_unfocused hollow` explicitly, even though it's already kitty's own default,
so a future kitty version or a theme can't quietly change it without this file noticing).

Hit for real while verifying that: a *focused* window's prompt showed a thin beam cursor, not the
configured block, even though `cursor_shape block` was right there in the config. Root cause:
`shell_integration enabled` (kitty's own zsh-integration feature -- jump-to-prompt, cwd tracking,
etc.) also switches the cursor to a beam at the shell prompt as one of its features, silently
overriding `cursor_shape` -- confirmed straight from kitty's own docs
(`docs/shell-integration.rst`, the `no-cursor` keyword's description: "Turn off changing of the
text cursor to a bar when editing shell command line"). Fixed by changing the value to
`shell_integration no-cursor` (a space-separated list of the *disabled* individual features, not
`enabled` plus `no-cursor` combined -- confirmed from the same doc: "By default, all integration
features are enabled... set to a space separated list of these values" -- the no-X keywords are
the whole value, not additions to "enabled"), which keeps every other shell-integration feature and
only stops that one cursor override. Verified for real: launched two kitty windows side by side,
screenshotted both together, one focused (solid pink block) and one not (hollow pink outline).

## AI agent tools: `ai-agents` module, `apps/mcp-server`, `local/`

Opt-in: every `ai-agents` step is `default=False` (bare `--run ai-agents` selects nothing -- verified).
`local/` is git-ignored *except* `.gitkeep`/`README.md` (`local/*` + `!` exceptions; a bare `local/`
rule can't be negated). Private pi extensions go in `local/pi-custom/*.ts` (symlinked into
`~/.pi/agent/extensions/` by `pi-custom-extensions`), private MCP plugins in `local/mcp-plugins/`.

`apps/mcp-server` is plain Node ESM (no build step). A plugin is `<dir>/<name>/index.mjs` exporting
`{description, tools:[{name, description, inputSchema?: (z)=>zodShape, handler(args, ctx)}]}`; tools are
exposed as `<plugin>_<tool>`. Which plugins load = config `mcp.enabledPlugins` (hub's MCP Server tab writes it
with `SetReplaceField`, like tmux segments). The server does **not** parse JSONC itself: it shells to
`python3 -m tui.jsonc_cli mcp-config` (falls back to defaults) so `jsonc.py` stays the one parser for Node.
`server.mjs --list-plugins` is what the hub tab and `ai-agents-verify` use. stdout is the protocol channel: log to stderr only.

pi wiring: `mcp-pi-wire` merges a `terminal-stuff` entry (`directTools: true`) into `~/.pi/agent/mcp.json`
(pi-mcp-adapter's file); `PI_CODING_AGENT_DIR` redirects both pi and these steps to a scratch dir.
Verified end to end with a small local model (gemma-4-E4B via llama-server, CPU-only, throwaway port) driven
through `pi -e <provider.ts> --mode json -p ...`: pi called `terminal-stuff_repo_list_modules` with args.

Gotchas hit: Terminal.Gui `Label` treats the first `_` as a hotkey marker, mangling tool names -- set
`HotKeySpecifier = new Rune(0xFFFF)` on labels showing them. `pi-install` runs `npm install -g` against the *real*
global prefix even under a scratch `HOME`, so skip it in sandbox tests. tmux socket paths under the scratchpad
are too long ("File name too long") -- use a short `TMUX_TMPDIR` like `/tmp/x`. `kill` of `llama-server` may need
`-9`; check `ss -ltn` for the port after.

## Public repo hygiene

- Never commit secrets, tokens, work hostnames, or employer-specific config.
- Private/machine-specific material goes in git-ignored files (`*.local`, `*.private`,
  `.private/`, `local/`, `secrets/`, `.env*`). Tracked configs source an optional local
  override rather than containing private values.
- Don't commit or push unless asked.

## Verifying changes

- `bash -n <script>` for syntax; run `shellcheck` if available.
- `./setup/doctor.sh` should run cleanly and exit 0 (exit 1 only with `--strict` and gaps).
- When adding a check to `doctor.sh`, use `check_cmd` / `check_paths` / `check_app` and
  give an install hint for each package manager; verify it against both a present and a
  missing tool.
