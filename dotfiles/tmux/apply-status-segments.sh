#!/usr/bin/env bash
# Applies tmux.statusLeft/statusRight from config.jsonc (search order/merge: config/README.md) as
# tmux2k's left/right plugin lists. Called from dotfiles/tmux/tmux.conf on every tmux start/reload
# (source-file), BEFORE tpm's `run` line loads tmux2k -- this is what makes the hub app's Status
# Segments tab choice (or a hand-edited config.jsonc) survive a full tmux restart. The hub's own
# "apply live" (`tmux set-option`, StatusSegmentsTab.cs) only reaches the currently-running
# server's in-memory state and is lost on `tmux kill-server` + restart, since nothing else ever
# read config.jsonc back into tmux -- this script is that missing piece.
#
# Best-effort and read-only: any failure (python3 missing, no config.jsonc yet, a parse error) is
# silently skipped so tmux2k just falls back to its own built-in defaults rather than breaking
# tmux startup.
set -u
repo="$1"

out=""
for py in python3 python; do
  command -v "$py" >/dev/null 2>&1 || continue
  out="$(PYTHONPATH="$repo/setup" PYTHONDONTWRITEBYTECODE=1 "$py" -m tui.jsonc_cli tmux-segments 2>/dev/null)" && break
  out=""
done
[ -z "$out" ] && exit 0

while IFS='=' read -r key val; do
  case "$key" in
    TS_LEFT)  [ -n "$val" ] && tmux set-option -g @tmux2k-left-plugins "$val" ;;
    TS_RIGHT) [ -n "$val" ] && tmux set-option -g @tmux2k-right-plugins "$val" ;;
  esac
done <<EOF
$out
EOF
exit 0
