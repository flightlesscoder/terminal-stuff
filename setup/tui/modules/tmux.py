"""Module: tmux — install, config from dotfiles/tmux/tmux.conf, tpm and its plugins, verification."""
from __future__ import annotations

import contextlib
import re
import shlex
import shutil
import tempfile
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import clone_step, pkg_run, pm_sudo, unix_only, which_check

MIN_VERSION = (3, 2)                                   # copy-command option
BLOCK = "tmux"
# tpm plugin repos (must match the @plugin lines in dotfiles/tmux/tmux.conf) -> dir name under ~/.tmux/plugins
PLUGIN_DIRS = ("tmux-sensible", "tmux2k", "tmux-which-key")


def conf_path(ctx: Ctx) -> Path:
    return ctx.home / ".tmux.conf"


def tpm_dir(ctx: Ctx) -> Path:
    return ctx.home / ".tmux" / "plugins" / "tpm"


def repo_conf(ctx: Ctx) -> Path:
    return ctx.root / "dotfiles" / "tmux" / "tmux.conf"


def block_body(ctx: Ctx) -> str:
    # @terminal-stuff-repo: read by apply-status-segments.sh (via dotfiles/tmux/tmux.conf) to find
    # setup/tui/jsonc_cli.py without hardcoding a path inside the repo's own tracked tmux.conf.
    return (f"set -g @terminal-stuff-repo {shlex.quote(str(ctx.root))}\n"
            f"source-file {shlex.quote(str(repo_conf(ctx)))}")


@contextlib.contextmanager
def private_server(ctx: Ctx) -> Iterator[dict]:
    """Environment for a throwaway tmux server that cannot see or affect a running one.

    tpm asks the tmux *server* (and inherited env) where plugins live, so without this a tmux
    session we happen to be running inside would leak its own paths into the test/installation.
    Own socket dir (TMUX_TMPDIR) + explicit plugin path for *this* home.
    """
    d = tempfile.mkdtemp(prefix="ts-tmux-", dir="/tmp")          # /tmp: unix socket paths are length-limited
    env = {"TMUX": "", "TMUX_TMPDIR": d, "TMUX_PLUGIN_MANAGER_PATH": str(tpm_dir(ctx).parent) + "/"}
    try:
        yield env
    finally:
        ctx.run(["tmux", "kill-server"], mutating=False, check=False, env=env, timeout=30)
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ config

def config_check(ctx: Ctx) -> Tuple[bool, str]:
    if ctx.block_current(conf_path(ctx), BLOCK, block_body(ctx)):
        return True, "~/.tmux.conf sources dotfiles/tmux/tmux.conf"
    if ctx.read_text(conf_path(ctx)).strip():
        return False, "existing ~/.tmux.conf will be backed up, then replaced"
    return False, "~/.tmux.conf missing"


def config_run(ctx: Ctx) -> str:
    if not repo_conf(ctx).is_file():
        raise StepError(f"missing {repo_conf(ctx)}")
    path = conf_path(ctx)
    existing = ctx.read_text(path)
    if f"terminal-stuff:{BLOCK}" in existing:
        changed = ctx.ensure_block(path, BLOCK, block_body(ctx))      # keeps anything outside the block
        return "updated managed block in ~/.tmux.conf" if changed else "~/.tmux.conf already up to date"
    # Not ours yet: write_text backs the old file up (date-stamped) before replacing it.
    ctx.write_text(path, ctx.render_block(BLOCK, block_body(ctx)))
    if existing.strip():
        where = ctx.last_backup.name if ctx.last_backup else "a .bak-<date> file next to it"
        return f"backed up the old ~/.tmux.conf to {where}, then installed the managed config"
    return "created ~/.tmux.conf"


# ------------------------------------------------------------------ plugins

def plugins_check(ctx: Ctx) -> Tuple[bool, str]:
    base = tpm_dir(ctx).parent
    missing = [d for d in PLUGIN_DIRS if not (base / d).is_dir()]
    return not missing, ("all plugins present" if not missing else f"missing: {', '.join(missing)}")


def plugins_run(ctx: Ctx) -> str:
    script = tpm_dir(ctx) / "bin" / "install_plugins"
    if not script.exists() and not ctx.dry_run:
        raise StepError("tpm is not installed; run the 'tpm-install' step first")
    if not ctx.which("tmux") and not ctx.dry_run:
        raise StepError("tmux is not installed")
    if "terminal-stuff:tmux" not in ctx.read_text(conf_path(ctx)) and not ctx.dry_run:
        raise StepError("~/.tmux.conf doesn't source our config; run the 'tmux-config' step first")
    if ctx.dry_run:
        ctx.run([script])                                   # logs the dry-run line
    else:
        with private_server(ctx) as env:                    # never talk to a tmux we're running inside
            ctx.run([script], env=env)
    ok, msg = plugins_check(ctx)
    if not ok and not ctx.dry_run:
        raise StepError(f"tpm finished but plugins are {msg}")
    return "tpm installed all plugins"


# ------------------------------------------------------------------ verification

def tmux_version(ctx: Ctx) -> Optional[Tuple[int, int]]:
    out = ctx.run(["tmux", "-V"], mutating=False, check=False).out
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def tmux_probe(ctx: Ctx) -> Tuple[bool, str]:
    """Read-only for your data: boot a throwaway tmux server (private socket) with the real
    ~/.tmux.conf and check the settings and bindings we promise. Returns (ok, message)."""
    if not ctx.which("tmux"):
        return False, "tmux is not installed"
    ver = tmux_version(ctx)
    if ver is None or ver < MIN_VERSION:
        return False, f"tmux {ver} is too old; need >= {'.'.join(map(str, MIN_VERSION))}"
    if "terminal-stuff:tmux" not in ctx.read_text(conf_path(ctx)):
        return False, "~/.tmux.conf doesn't source our config (run the 'tmux-config' step)"
    ok, msg = plugins_check(ctx)
    if not ok:
        return False, f"tmux plugins {msg} (run the 'tmux-plugins' step)"
    if not ctx.which("python3"):
        return False, "python3 is required by tmux-which-key"

    def table(q, name: str) -> str:
        return q("list-keys", "-T", name)

    def binding(text: str, key: str) -> str:
        m = re.search(rf"^bind-key\s+(?:-\S+\s+)*-T\s+\S+\s+{re.escape(key)}\s+(.*)$", text, re.M)
        return m.group(1) if m else ""

    with private_server(ctx) as env:
        base = ["tmux"]
        q = lambda *a: ctx.run(base + list(a), mutating=False, check=False, env=env, timeout=30).out  # noqa: E731
        ctx.run(base + ["-f", str(conf_path(ctx)), "new-session", "-d", "-s", "verify"],
                mutating=False, env=env, timeout=60)
        for _ in range(10):                                 # plugins finish loading asynchronously
            space = binding(table(q, "prefix"), "Space")
            if space and space.strip() != "next-layout":    # next-layout is tmux's default Space
                break
            time.sleep(1)
        prefix_tbl, root_tbl = table(q, "prefix"), table(q, "root")
        checks = [
            ("mouse is on", q("show", "-gv", "mouse").strip() == "on"),
            ("default-terminal is tmux-256color", q("show", "-gv", "default-terminal").strip() == "tmux-256color"),
            ("terminal-overrides has ',xterm-256color:RGB'", "xterm-256color:RGB" in q("show", "-g", "terminal-overrides")),
            ("@tmux2k-theme is onedark", q("show", "-gv", "@tmux2k-theme").strip() == "onedark"),
            ("prefix+m toggles the mouse", "mouse" in binding(prefix_tbl, "m")),
            ("prefix+Space is taken over by tmux-which-key", bool(space) and space.strip() != "next-layout"),
            ("Shift+right-click menu is bound", "display-menu" in binding(root_tbl, "S-MouseDown3Pane")),
            ("copy-command is set (clipboard)", bool(q("show", "-s", "copy-command").strip())),
            ("allow-passthrough is on (sixel)", q("show", "-gv", "allow-passthrough").strip() == "on"),
            ("terminal-features has sixel", "sixel" in q("show", "-g", "terminal-features")),
            ("tmux itself was built with --enable-sixel", q("display", "-p", "#{sixel_support}").strip() == "1"),
        ]
    for label, ok in checks:
        ctx.log.info("tmux verify: %-48s %s", label, "ok" if ok else "FAILED")
    bad = [label for label, ok in checks if not ok]
    if bad:
        return False, ("tmux config isn't behaving as expected:\n  - " + "\n  - ".join(bad)
                       + "\n  (see the log for details; try `tmux kill-server` and re-run)")
    return True, f"tmux {ver[0]}.{ver[1]}: all {len(checks)} settings/bindings verified in a fresh server"


def tmux_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (nothing was actually changed)"
    ok, msg = tmux_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


def tmux_verify_check(ctx: Ctx) -> Tuple[bool, str]:
    ok, msg = tmux_probe(ctx)
    return ok, msg.splitlines()[0]


# ------------------------------------------------------------------ module

def build() -> Module:
    tpm_c, tpm_r = clone_step("https://github.com/tmux-plugins/tpm.git", tpm_dir, "tpm")
    S = Step
    return Module("tmux", "tmux (config, tpm, plugins)",
                  "tmux with the repo's config, tpm, tmux-sensible, tmux2k (onedark) and tmux-which-key.", [
        S("tmux-install", "Install tmux", "Install tmux with the system package manager.",
          which_check("tmux"), pkg_run("tmux", apt="tmux", dnf="tmux", brew="tmux"), pm_sudo, unix_only),
        S("tmux-config", "tmux: config (backs up the old one)",
          "Back up an existing ~/.tmux.conf to ~/.tmux.conf.bak-<date-time>, then install a managed one that sources dotfiles/tmux/tmux.conf "
          "(mouse on + ^B m toggle, tmux-256color, RGB overrides, onedark, clipboard, context menu). Private tweaks: ~/.tmux.local.conf.",
          config_check, config_run, supported=unix_only),
        S("tpm-install", "Install tpm (plugin manager)", "Clone tmux-plugins/tpm into ~/.tmux/plugins/tpm.",
          tpm_c, tpm_r, supported=unix_only),
        S("tmux-plugins", "Install tmux plugins", "tpm install: tmux-sensible, tmux2k (2kabhishek), tmux-which-key (needs python3).",
          plugins_check, plugins_run, supported=unix_only),
        S("tmux-verify", "Verify tmux setup",
          "Boot a throwaway tmux server (private socket; your running tmux is untouched) with ~/.tmux.conf and check mouse, terminal, theme, toggle, which-key, menu and clipboard. Read-only.",
          tmux_verify_check, tmux_verify, supported=unix_only),
    ])
