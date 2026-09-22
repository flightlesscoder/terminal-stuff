"""`python3 -m tui.jsonc_cli [check|tmux-segments]` -- script-friendly config resolve, for
doctor.sh and dotfiles/tmux/apply-status-segments.sh, without booting the whole TUI.

`check` (default, no args): prints "OK: valid: N paths, L+R tmux segments (K layer(s))" and
exits 0, or "ERROR: <message>" and exits 1. Resolves from the current working directory, same as
jsonc.resolve() is documented to for "as it would load from the current directory".

`tmux-segments`: prints `TS_LEFT=...`/`TS_RIGHT=...` (space-separated segment names) for
apply-status-segments.sh to `tmux set-option` with -- see that script and dotfiles/tmux/tmux.conf
for why this needs to run on every tmux start, not just live from the hub app.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import jsonc

ROOT = Path(__file__).resolve().parents[2]


def cmd_check() -> int:
    home = Path.home()
    try:
        cfg, used = jsonc.resolve(ROOT, Path.cwd(), home)
    except jsonc.JsoncError as e:
        print(f"ERROR: {e}")
        return 1
    n_paths = len(cfg.get("paths", []))
    tmux_cfg = cfg.get("tmux", {})
    n_left, n_right = len(tmux_cfg.get("statusLeft", [])), len(tmux_cfg.get("statusRight", []))
    user_config = home / ".config" / "terminal-stuff" / jsonc.CONFIG_FILENAME
    print(f"OK: valid: {n_paths} paths, {n_left}+{n_right} tmux segments ({len(used)} layer(s))"
         f"{'; no user config yet' if user_config not in used else ''}")
    return 0


def cmd_tmux_segments() -> int:
    home = Path.home()
    try:
        cfg, _used = jsonc.resolve(ROOT, Path.cwd(), home)
    except jsonc.JsoncError:
        return 1                                          # caller falls back to tmux2k's own defaults
    tmux_cfg = cfg.get("tmux", {})
    left = tmux_cfg.get("statusLeft", [])
    right = tmux_cfg.get("statusRight", [])
    if not isinstance(left, list) or not isinstance(right, list):
        return 1
    print(f"TS_LEFT={' '.join(str(s) for s in left)}")
    print(f"TS_RIGHT={' '.join(str(s) for s in right)}")
    return 0


def main() -> int:
    if sys.argv[1:2] == ["tmux-segments"]:
        return cmd_tmux_segments()
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
