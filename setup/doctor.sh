#!/usr/bin/env bash
# doctor.sh — report which tools of my environment are installed on this machine.
#
# Read-only: it never installs or modifies anything. Works on Linux (Bazzite/Fedora,
# Ubuntu/Debian), macOS (Intel + ARM) and Windows via Git Bash/MSYS/WSL.
# Must stay compatible with bash 3.2 (stock macOS): no associative arrays, no ${var,,}.
#
# Usage: setup/doctor.sh [--no-color] [--strict] [--only-missing] [-h]
#   --strict        exit 1 if anything is missing (default: always exit 0)
#   --only-missing  hide the items that were found

set -u
: "${LOCALAPPDATA:=}" "${APPDATA:=}"   # Windows-only; unset elsewhere

USE_COLOR=1
STRICT=0
ONLY_MISSING=0
for arg in "$@"; do
  case "$arg" in
    --no-color) USE_COLOR=0 ;;
    --strict) STRICT=1 ;;
    --only-missing) ONLY_MISSING=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
[ -t 1 ] || USE_COLOR=0
[ -n "${NO_COLOR:-}" ] && USE_COLOR=0

if [ "$USE_COLOR" = 1 ]; then
  C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_OK=; C_BAD=; C_DIM=; C_BOLD=; C_OFF=
fi

# ---------------------------------------------------------------- OS detection
OS=unknown        # linux | macos | windows
DISTRO=unknown    # bazzite | fedora | ubuntu | debian | macos | windows | ...
ARCH=$(uname -m)
case "$(uname -s)" in
  Darwin) OS=macos; DISTRO=macos ;;
  Linux)
    OS=linux
    if [ -r /etc/os-release ]; then
      # shellcheck disable=SC1091
      DISTRO=$(. /etc/os-release && echo "${ID:-linux}")
    fi
    if grep -qi microsoft /proc/version 2>/dev/null; then IS_WSL=1; else IS_WSL=0; fi
    ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows; DISTRO=windows ;;
esac
: "${IS_WSL:=0}"

# Extend PATH with the usual non-default locations so we find tools the same way an
# interactive shell would (Homebrew on Linux/macOS, ~/.local/bin, dotnet, cargo).
for p in /home/linuxbrew/.linuxbrew/bin /opt/homebrew/bin /usr/local/bin \
         "$HOME/.local/bin" "$HOME/.dotnet" "$HOME/.cargo/bin"; do
  [ -d "$p" ] && case ":$PATH:" in *":$p:"*) ;; *) PATH="$PATH:$p" ;; esac
done

# Package manager, used only for install hints.
PM=
if   command -v brew    >/dev/null 2>&1 && [ "$DISTRO" = macos ];          then PM=brew
elif command -v rpm-ostree >/dev/null 2>&1 && [ "$DISTRO" = bazzite ];     then PM=brew   # immutable: prefer brew/flatpak
elif command -v apt-get >/dev/null 2>&1; then PM=apt
elif command -v dnf     >/dev/null 2>&1; then PM=dnf
elif command -v brew    >/dev/null 2>&1; then PM=brew
elif command -v winget  >/dev/null 2>&1; then PM=winget
elif command -v pacman  >/dev/null 2>&1; then PM=pacman
fi

have() { command -v "$1" >/dev/null 2>&1; }
first_line() { head -n 1; }

# Flatpak / snap presence checks (cheap; skipped if the tool is absent).
have_flatpak() { have flatpak && flatpak info "$1" >/dev/null 2>&1; }
have_snap()    { have snap && snap list "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------- reporting
FOUND=0
MISSING=0
MISSING_LIST=""

# report <label> <found:0|1> <detail> [hint]
report() {
  local label=$1 ok=$2 detail=$3 hint=${4:-}
  if [ "$ok" = 1 ]; then
    FOUND=$((FOUND + 1))
    [ "$ONLY_MISSING" = 1 ] && return
    printf '  %s✔%s %-16s %s%s%s\n' "$C_OK" "$C_OFF" "$label" "$C_DIM" "$detail" "$C_OFF"
  else
    MISSING=$((MISSING + 1))
    MISSING_LIST="$MISSING_LIST $label"
    printf '  %s✘%s %-16s %s%s%s\n' "$C_BAD" "$C_OFF" "$label" "$C_DIM" "${hint:+fix: $hint}" "$C_OFF"
  fi
}

section() { [ "$ONLY_MISSING" = 1 ] || printf '\n%s%s%s\n' "$C_BOLD" "$1" "$C_OFF"; }

# install_hint <apt-pkg> <dnf-pkg> <brew-pkg> <winget-id>   ("-" = not applicable)
install_hint() {
  local pkg
  case "$PM" in
    apt) pkg=$1; [ "$pkg" != - ] && echo "sudo apt install $pkg" ;;
    dnf) pkg=$2; [ "$pkg" != - ] && echo "sudo dnf install $pkg" ;;
    brew) pkg=$3; [ "$pkg" != - ] && echo "brew install $pkg" ;;
    winget) pkg=$4; [ "$pkg" != - ] && echo "winget install $pkg" ;;
    pacman) pkg=$1; [ "$pkg" != - ] && echo "sudo pacman -S $pkg" ;;
  esac
}

# check_cmd <label> <command> <version-args> <apt> <dnf> <brew> <winget>
check_cmd() {
  local label=$1 cmd=$2 vargs=$3 path ver
  if have "$cmd"; then
    path=$(command -v "$cmd")
    # shellcheck disable=SC2086
    ver=$("$cmd" $vargs 2>&1 | first_line)
    report "$label" 1 "${ver:-?}  ($path)"
  else
    report "$label" 0 "" "$(install_hint "$4" "$5" "$6" "$7")"
  fi
}

# check_dirs <label> <hint> <path>...   — installed if any path exists
check_paths() {
  local label=$1 hint=$2 p; shift 2
  for p in "$@"; do
    if [ -e "$p" ]; then report "$label" 1 "$p"; return; fi
  done
  report "$label" 0 "" "$hint"
}

# ---------------------------------------------------------------- header
printf '%sdoctor%s  os=%s distro=%s arch=%s%s pkg-mgr=%s\n' "$C_BOLD" "$C_OFF" \
  "$OS" "$DISTRO" "$ARCH" "$([ "$IS_WSL" = 1 ] && echo ' (WSL)')" "${PM:-none}"
[ "$DISTRO" = bazzite ] && printf '%s(immutable OS: prefer brew / flatpak / distrobox over rpm-ostree layering)%s\n' "$C_DIM" "$C_OFF"

# ---------------------------------------------------------------- shell & terminal
section "Shell & terminal"
check_cmd zsh  zsh  --version zsh zsh zsh -
check_cmd tmux tmux -V tmux tmux tmux -
# tmux plugins (tpm + the ones our config lists); doctor only looks, ./setup/setup.sh installs them.
tmux_missing=
for pl in tpm tmux-sensible tmux2k tmux-which-key; do
  [ -d "$HOME/.tmux/plugins/$pl" ] || tmux_missing="$tmux_missing $pl"
done
if [ -z "$tmux_missing" ]; then
  report "tmux plugins" 1 "tpm, tmux-sensible, tmux2k, tmux-which-key (~/.tmux/plugins)"
else
  report "tmux plugins" 0 "" "./setup/setup.sh -> tmux module (missing:$tmux_missing)"
fi
# Config (config/README.md): layered JSONC, resolved the same way a tool run from $PWD would.
# doctor.sh stays read-only (see Conventions) -- ./setup/setup.sh's config-init step is what
# creates ~/.config/terminal-stuff/config.jsonc; this only reports whether one is needed/valid.
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if have python3; then
  config_out=$(PYTHONPATH="$REPO_ROOT/setup" python3 -m tui.jsonc_cli 2>&1)
  case "$config_out" in
    OK:*) report config 1 "${config_out#OK: }" ;;
    *) report config 0 "" "${config_out#ERROR: }  (./setup/setup.sh -> config module)" ;;
  esac
else
  report config 0 "" "needs python3 to check"
fi

# Terminal Stuff Hub (apps/hub): built, and present in the tmux-which-key menu.
if [ -f "$REPO_ROOT/apps/hub/bin/hub.dll" ]; then
  report "hub app" 1 "$REPO_ROOT/apps/hub/bin/hub.dll"
else
  report "hub app" 0 "" "./setup/setup.sh -> hub module (needs the .NET 10 SDK)"
fi
if grep -qs 'terminal-stuff:hub' "$HOME/.tmux/plugins/tmux-which-key/config.yaml"; then
  report "hub menu entry" 1 "in tmux-which-key menu (prefix + Space, h)"
else
  report "hub menu entry" 0 "" "./setup/setup.sh -> hub module ('hub-menu' step; needs the tmux module first)"
fi
check_cmd ssh  ssh  -V openssh-client openssh-clients openssh Microsoft.OpenSSH.Beta
check_cmd fzf  fzf  --version fzf fzf fzf junegunn.fzf
check_cmd ripgrep rg --version ripgrep ripgrep ripgrep BurntSushi.ripgrep.MSVC

# fd: Debian/Ubuntu's apt package installs the binary as "fdfind" (name clash avoidance).
if have fd; then report fd 1 "$(fd --version 2>&1 | first_line)  ($(command -v fd))"
elif have fdfind; then report fd 1 "$(fdfind --version 2>&1 | first_line)  ($(command -v fdfind), not symlinked to 'fd')"
else report fd 0 "" "$(install_hint fd-find fd-find fd fd)"
fi

# tree-sitter-cli: nvim-treesitter now requires the real CLI (not the npm package).
check_cmd tree-sitter tree-sitter --version - - tree-sitter -

if have cc; then report "C compiler" 1 "$(command -v cc)"
elif have gcc; then report "C compiler" 1 "$(command -v gcc)"
elif have clang; then report "C compiler" 1 "$(command -v clang)"
else report "C compiler" 0 "" "$(install_hint build-essential gcc gcc -)  (macOS: xcode-select --install)"
fi

# LazyVim: the starter's own marker file, plus how many plugins lazy.nvim has resolved.
if [ -f "$HOME/.config/nvim/lua/config/lazy.lua" ]; then
  n_plugins=0
  [ -r "$HOME/.config/nvim/lazy-lock.json" ] && n_plugins=$(grep -c '": {' "$HOME/.config/nvim/lazy-lock.json" 2>/dev/null || echo 0)
  if [ "$n_plugins" -gt 0 ]; then
    report lazyvim 1 "~/.config/nvim ($n_plugins plugins locked)"
  else
    report lazyvim 0 "" "installed but no plugins synced yet: ./setup/setup.sh -> neovim module ('lazyvim-plugins' step)"
  fi
else
  report lazyvim 0 "" "./setup/setup.sh -> neovim module ('lazyvim-config' step)"
fi

# lazyvim-dev: the lang extras (typescript/json/python/dotnet/sql) + bash/powershell LSPs.
if [ -r "$HOME/.config/nvim/lazyvim.json" ] && grep -q "lang.typescript" "$HOME/.config/nvim/lazyvim.json" 2>/dev/null; then
  mason="$HOME/.local/share/nvim/mason/packages"
  if [ -d "$mason/bash-language-server" ] && [ -d "$mason/powershell-editor-services" ]; then
    report "lazyvim-dev" 1 "lang extras enabled; bash/powershell LSPs installed"
  else
    report "lazyvim-dev" 0 "" "./setup/setup.sh -> lazyvim-dev module ('lazyvim-dev-sync' step)"
  fi
else
  report "lazyvim-dev" 0 "" "./setup/setup.sh -> lazyvim-dev module"
fi

# speak-background.sh: deployed by ./setup/setup.sh (module "speech"), configured by the hub app's
# Speech tab. Reports muted/unmuted (the SPEAK-LINE commented or not) and which engine is present.
SPEAK_SCRIPT="$HOME/apps/scripts/speak-background.sh"
if [ -f "$SPEAK_SCRIPT" ]; then
  if grep -qE '^\s*#\s*_speak_now "\$TEXT" &' "$SPEAK_SCRIPT"; then muted=" (muted)"; else muted=""; fi
  case "$OS" in
    macos) engine=say ;;
    *)
      engine=none
      for e in spd-say espeak-ng festival flite; do have "$e" && { engine=$e; break; }; done
      { have powershell.exe || have pwsh; } && [ "$engine" = none ] && engine=powershell
      ;;
  esac
  if [ "$engine" = none ]; then
    report speech 0 "" "$SPEAK_SCRIPT exists but no engine found (install spd-say, espeak-ng, festival or flite)"
  else
    report speech 1 "$SPEAK_SCRIPT (engine: $engine)$muted"
  fi
else
  report speech 0 "" "./setup/setup.sh -> speech module ('speech-install' step)"
fi

ZSH_DIR=${ZSH:-$HOME/.oh-my-zsh}
check_paths oh-my-zsh 'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"' \
  "$ZSH_DIR/oh-my-zsh.sh"

ZSH_CUSTOM_DIR=${ZSH_CUSTOM:-$ZSH_DIR/custom}
BREW_PREFIX=
have brew && BREW_PREFIX=$(brew --prefix 2>/dev/null)
check_paths "pure prompt" 'git clone https://github.com/sindresorhus/pure.git ~/.zsh/pure  (then symlink pure.zsh -> $ZSH_CUSTOM/themes/pure.zsh-theme)' \
  "$ZSH_CUSTOM_DIR/themes/pure.zsh-theme" \
  "$ZSH_CUSTOM_DIR/plugins/pure/pure.zsh" \
  "$HOME/.zsh/pure/pure.zsh" \
  "${BREW_PREFIX:+$BREW_PREFIX/share/zsh/site-functions/prompt_pure_setup}"

check_paths "scm breeze" './setup/setup.sh -> terminal-env module (scm-breeze-* steps; skips loading itself when $CLAUDECODE is set)' \
  "$HOME/.scm_breeze/scm_breeze.sh"

# Hyper: CLI is optional, so also look for the app bundle and its config.
hyper_found=
for p in "$(command -v hyper 2>/dev/null)" /Applications/Hyper.app /opt/Hyper/hyper \
         "$HOME/Applications/Hyper.AppImage" "$LOCALAPPDATA/hyper/Hyper.exe" \
         "$HOME/AppData/Local/hyper/Hyper.exe"; do
  [ -n "$p" ] && [ -e "$p" ] && { hyper_found=$p; break; }
done
if [ -n "$hyper_found" ]; then
  cfg=; [ -f "$HOME/.hyper.js" ] && cfg="  config: ~/.hyper.js"
  # hyper-install records which release it fetched; sixel only ever shipped in a v4 canary build.
  tag=; [ -r "$HOME/.cache/terminal-stuff/hyper-installed-tag.txt" ] && tag=$(cat "$HOME/.cache/terminal-stuff/hyper-installed-tag.txt")
  case "$tag" in
    *canary*) report hyper 1 "$hyper_found$cfg  ($tag, sixel-capable)" ;;
    *) report hyper 0 "$hyper_found$cfg -- not the sixel build" "./setup/setup.sh -> terminal-env module ('hyper-install' step) for the sixel-capable canary build" ;;
  esac
else
  report hyper 0 "" "./setup/setup.sh -> terminal-env module  (installs the sixel-capable canary build)"
fi

# kitty: optional trial terminal (module "kitty", not installed by default).
if have kitty; then report kitty 1 "$(kitty --version 2>&1 | first_line)  ($(command -v kitty))"
else report kitty 0 "" "./setup/setup.sh -> kitty module (optional)"
fi

# Nerd Font: a *text* font patched with icons (Symbols-only fonts are just fallbacks, so ignored).
nerd_fams=
if have fc-list; then
  nerd_fams=$(fc-list : family 2>/dev/null | tr ',' '\n' | sed 's/^ *//' | grep 'Nerd Font' | grep -v '^Symbols' | sort -u)
fi
if [ -z "$nerd_fams" ]; then   # no fontconfig (macOS) or nothing listed: look for font files
  for d in "$HOME/Library/Fonts" /Library/Fonts "$HOME/.local/share/fonts"; do
    if [ -n "$(find "$d" \( -iname '*NerdFont*.ttf' -o -iname '*NerdFont*.otf' \) 2>/dev/null | head -n 1)" ]; then
      nerd_fams="(Nerd Font files in $d)"; break
    fi
  done
fi
if [ -n "$nerd_fams" ]; then
  n_fams=$(printf '%s\n' "$nerd_fams" | wc -l | tr -d ' ')
  if printf '%s\n' "$nerd_fams" | grep -qx 'JetBrainsMono Nerd Font Mono'; then
    report "nerd font" 1 "JetBrainsMono Nerd Font Mono$([ "$n_fams" -gt 1 ] && echo " (+$((n_fams - 1)) more)")"
  else
    report "nerd font" 1 "$(printf '%s\n' "$nerd_fams" | head -n 3 | tr '\n' ',' | sed 's/,$//')  (preferred: JetBrainsMono Nerd Font Mono)"
  fi
else
  report "nerd font" 0 "" "./setup/setup.sh -> 'Install JetBrainsMono Nerd Font' (only icon-fallback fonts, if any, are installed)"
fi

# Is Hyper actually told to use it? (only meaningful once ~/.hyper.js exists)
if [ -f "$HOME/.hyper.js" ]; then
  hyper_font=$(grep -E '^[[:space:]]*fontFamily[[:space:]]*:' "$HOME/.hyper.js" | head -n 1 | sed 's/^[[:space:]]*//')
  case "$hyper_font" in
    *"Nerd Font"*) report "hyper font" 1 "Nerd Font set in ~/.hyper.js" ;;
    *) report "hyper font" 0 "" "./setup/setup.sh -> 'Hyper: use Nerd Font'  (current: ${hyper_font:-fontFamily not set})" ;;
  esac
else
  report "hyper font" 0 "" "no ~/.hyper.js yet: ./setup/setup.sh -> 'Hyper: config'"
fi

# Clipboard: list every helper found, then say which one this session should use.
clip_found=
for c in wl-copy xclip xsel pbcopy clip.exe win32yank.exe clip termux-clipboard-set; do
  have "$c" && clip_found="$clip_found $c"
done
clip_found=${clip_found# }
if [ -n "$clip_found" ]; then
  preferred=
  case "$OS" in
    macos) preferred=pbcopy ;;
    windows) preferred=clip ;;
    linux)
      if [ "$IS_WSL" = 1 ] && have clip.exe; then preferred=clip.exe
      elif [ -n "${WAYLAND_DISPLAY:-}" ] && have wl-copy; then preferred=wl-copy
      elif [ -n "${DISPLAY:-}" ] && have xclip; then preferred=xclip
      elif [ -n "${DISPLAY:-}" ] && have xsel; then preferred=xsel
      fi ;;
  esac
  [ -z "$preferred" ] && preferred=${clip_found%% *}
  report clipboard 1 "using: $preferred  (available: $clip_found)  session=${XDG_SESSION_TYPE:-n/a}"
else
  case "$OS" in
    macos) h="pbcopy ships with macOS (check PATH)" ;;
    linux) h="wl-clipboard (Wayland) or xclip (X11): $(install_hint xclip xclip xclip -)" ;;
    *) h="clip.exe ships with Windows; or install win32yank" ;;
  esac
  report clipboard 0 "" "$h"
fi

# ---------------------------------------------------------------- dev tools
section "Development tools"
check_cmd git  git  --version git git git Git.Git
check_cmd curl curl --version curl curl curl cURL.cURL
check_cmd wget wget --version wget wget wget -
check_cmd neovim nvim --version neovim neovim neovim Neovim.Neovim
check_cmd dotnet dotnet --version dotnet-sdk-8.0 dotnet-sdk-8.0 dotnet-sdk Microsoft.DotNet.SDK.8
check_cmd node node --version nodejs nodejs node OpenJS.NodeJS.LTS
check_cmd npm  npm  --version npm npm node -
check_cmd ruby ruby --version ruby ruby ruby RubyInstallerTeam.Ruby.3.3
check_cmd jq   jq   --version jq jq jq jqlang.jq

# lazygit / bottom: apt has no lazygit package (needs a third-party PPA) and bottom is patchy
# across distros, so ./setup/setup.sh installs both from upstream's own releases on Linux.
if have lazygit; then report lazygit 1 "$(lazygit --version 2>&1 | first_line)  ($(command -v lazygit))"
else report lazygit 0 "" "./setup/setup.sh -> extras module  (brew install lazygit on macOS)"
fi
if have lazydocker; then report lazydocker 1 "$(lazydocker --version 2>&1 | first_line)  ($(command -v lazydocker))"
else report lazydocker 0 "" "./setup/setup.sh -> extras module  (brew install lazydocker on macOS)"
fi
if have btm; then report bottom 1 "$(btm --version 2>&1 | first_line)  ($(command -v btm))"
else report bottom 0 "" "./setup/setup.sh -> extras module  (brew install bottom on macOS)"
fi
if have gdu; then report gdu 1 "$(gdu --version 2>&1 | first_line)  ($(command -v gdu))"
else report gdu 0 "" "./setup/setup.sh -> extras module  (brew install gdu on macOS)"
fi
if have glow; then report glow 1 "$(glow --version 2>&1 | first_line)  ($(command -v glow))"
else report glow 0 "" "./setup/setup.sh -> extras module  (brew install glow on macOS)"
fi
check_cmd zoxide zoxide --version zoxide zoxide zoxide ajeetdsouza.zoxide

# python: python3 is canonical on *nix; Windows often only has python / py.
py=
for c in python3 python py; do have "$c" && { py=$c; break; }; done
if [ -n "$py" ]; then
  report python 1 "$($py --version 2>&1 | first_line)  ($(command -v "$py"))"
else
  report python 0 "" "$(install_hint python3 python3 python Python.Python.3.12)"
fi

# Node version manager: n (a binary) or nvm (a shell function, so look for its files).
nvm_sh=
for p in "${NVM_DIR:-}/nvm.sh" "$HOME/.nvm/nvm.sh" "${XDG_CONFIG_HOME:-$HOME/.config}/nvm/nvm.sh" \
         "${BREW_PREFIX:+$BREW_PREFIX/opt/nvm/nvm.sh}"; do
  [ -f "$p" ] && { nvm_sh=$p; break; }
done
nvm_detail=
have n && nvm_detail="n $(n --version 2>&1 | first_line)  ($(command -v n))"
[ -n "$nvm_sh" ] && nvm_detail="${nvm_detail:+$nvm_detail; }nvm ($nvm_sh)"
if [ -n "$nvm_detail" ]; then
  report "node version mgr" 1 "$nvm_detail"
else
  report "node version mgr" 0 "" "./setup/setup.sh -> node module  (tj/n on Linux/macOS/WSL; nvm-windows on native Windows)"
fi

# ---------------------------------------------------------------- AI agent tools
# Optional/opt-in: ./setup/setup.sh -> ai-agents module (never pre-selected there either).
section "AI agent tools (optional)"
if have pi; then
  report pi 1 "$(pi --version 2>&1 | first_line)  ($(command -v pi))"
else
  report pi 0 "" "./setup/setup.sh -> ai-agents module ('pi-install' step)"
fi
MCP_DIR="$REPO_ROOT/apps/mcp-server"
if [ -d "$MCP_DIR/node_modules/@modelcontextprotocol/sdk" ]; then
  report "mcp server" 1 "$MCP_DIR"
else
  report "mcp server" 0 "" "./setup/setup.sh -> ai-agents module ('mcp-server-install' step)"
fi
PI_AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"
if [ -f "$PI_AGENT_DIR/mcp.json" ] && grep -q "$MCP_DIR/server.mjs" "$PI_AGENT_DIR/mcp.json" 2>/dev/null; then
  report "mcp -> pi" 1 "$PI_AGENT_DIR/mcp.json"
else
  report "mcp -> pi" 0 "" "./setup/setup.sh -> ai-agents module ('mcp-pi-wire' step)"
fi
# local/pi-custom is git-ignored, so a fresh clone legitimately has nothing there: only flag files that aren't linked.
for f in "$REPO_ROOT"/local/pi-custom/*.ts; do
  [ -e "$f" ] || continue
  if [ "$PI_AGENT_DIR/extensions/$(basename "$f")" -ef "$f" ]; then
    report "pi ext $(basename "$f")" 1 "linked from local/pi-custom"
  else
    report "pi ext $(basename "$f")" 0 "" "./setup/setup.sh -> ai-agents module ('pi-custom-extensions' step)"
  fi
done

# ---------------------------------------------------------------- GUI apps
# Apps can come from many places: PATH, flatpak, snap, /Applications, AppImage, Program Files.
check_app() {
  local label=$1 cmd=$2 flatpak_id=$3 snap_name=$4 mac_app=$5 win_glob=$6 hint=$7 p
  if have "$cmd"; then report "$label" 1 "$(command -v "$cmd")"; return; fi
  if [ -n "$flatpak_id" ] && have_flatpak "$flatpak_id"; then report "$label" 1 "flatpak: $flatpak_id"; return; fi
  if [ -n "$snap_name" ] && have_snap "$snap_name"; then report "$label" 1 "snap: $snap_name"; return; fi
  if [ -n "$mac_app" ]; then
    for p in "/Applications/$mac_app.app" "$HOME/Applications/$mac_app.app"; do
      [ -d "$p" ] && { report "$label" 1 "$p"; return; }
    done
  fi
  if [ "$OS" = windows ] && [ -n "$win_glob" ]; then
    for p in $win_glob; do [ -e "$p" ] && { report "$label" 1 "$p"; return; }; done
  fi
  for p in "$HOME/Applications/$label"*.AppImage "$HOME/Applications/${label}"*.appimage; do
    [ -e "$p" ] && { report "$label" 1 "$p"; return; }
  done
  report "$label" 0 "" "$hint"
}

section "Apps"
check_app spotify spotify com.spotify.Client spotify Spotify \
  "$APPDATA/Spotify/Spotify.exe" \
  "flatpak install flathub com.spotify.Client  (brew install --cask spotify on macOS)"
check_app obsidian obsidian md.obsidian.Obsidian obsidian Obsidian \
  "$LOCALAPPDATA/Programs/Obsidian/Obsidian.exe" \
  "flatpak install flathub md.obsidian.Obsidian  (brew install --cask obsidian on macOS)"
check_app firefox firefox org.mozilla.firefox firefox Firefox \
  "/c/Program Files/Mozilla Firefox/firefox.exe" \
  "flatpak install flathub org.mozilla.firefox  (brew install --cask firefox on macOS)"

# ---------------------------------------------------------------- summary
printf '\n%s%d found%s, %s%d missing%s' "$C_OK" "$FOUND" "$C_OFF" "$C_BAD" "$MISSING" "$C_OFF"
[ "$MISSING" -gt 0 ] && printf ' —%s' "$MISSING_LIST"
printf '\n'

[ "$STRICT" = 1 ] && [ "$MISSING" -gt 0 ] && exit 1
exit 0
