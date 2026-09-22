#!/usr/bin/env bash
# Makes new tmux windows/panes spawn zsh, matching kitty (dotfiles/kitty/kitty.conf's `shell`
# line). Without this, tmux's default-shell falls back to $SHELL / the passwd-database login
# shell -- which stays bash unless the user's account was actually `chsh`'d to zsh, something the
# zsh-install/zsh-env setup steps don't do (chsh needs the target shell listed in /etc/shells,
# which isn't guaranteed for a Homebrew-installed zsh, and changes system account state outside
# this repo's scope -- see CLAUDE.md).
#
# Re-resolved on every tmux start (called from dotfiles/tmux/tmux.conf via run-shell), not baked
# in once, so it keeps working if zsh's install location ever changes. Best-effort: if zsh can't
# be found at all, this is a silent no-op and tmux just keeps using its own fallback.
set -u

z="$(command -v zsh 2>/dev/null)"
if [ -z "$z" ]; then
  for cand in /home/linuxbrew/.linuxbrew/bin/zsh /opt/homebrew/bin/zsh /usr/local/bin/zsh /usr/bin/zsh /bin/zsh; do
    [ -x "$cand" ] && { z="$cand"; break; }
  done
fi
[ -n "$z" ] && tmux set-option -g default-shell "$z"
exit 0
