"""Module: kitty -- optional trial terminal, side by side with Hyper.

Not a Hyper replacement (yet): the plan is to run both for a while and compare. Doesn't do sixel
and never will -- kitty deliberately only implements its own graphics protocol, which is more
capable (RGBA, no palette limit) and is on by default with zero config, unlike Hyper's sixel
support which needed the canary build (see terminal_env.py's hyper_install).
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import pm_sudo, unix_only
from .terminal_env import HYPER_FONT_STACK          # reuse the same font stack as Hyper

INSTALLER_URL = "https://sw.kovidgoyal.net/kitty/installer.sh"


def config_path(ctx: Ctx) -> Path:
    return ctx.home / ".config" / "kitty" / "kitty.conf"


def install_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("kitty")
    if not p:
        return False, "kitty not found"
    ver = ctx.run([p, "--version"], mutating=False, check=False).out.strip()
    return True, f"{ver}  ({p})"


def install_run(ctx: Ctx) -> str:
    if ctx.osinfo.pm == "brew" and ctx.which("brew"):
        ctx.run(["brew", "install", "kitty"])
    elif ctx.osinfo.pm in ("apt", "dnf"):
        ctx.install_pkg(apt="kitty", dnf="kitty")
    else:
        # kitty's own recommended install for everything else: a self-contained installer script
        # that unpacks a prebuilt kitty.app/kitty into ~/.local/kitty.app, with a `kitty` symlink.
        ctx.run(["sh", "-c", f"curl -fsSL {INSTALLER_URL} | sh /dev/stdin"])
        ctx.symlink(ctx.home / ".local" / "kitty.app" / "bin" / "kitty", ctx.home / ".local" / "bin" / "kitty")
    if ctx.dry_run:
        return "would install kitty"
    if not ctx.which("kitty"):
        raise StepError("installed but 'kitty' is still not on PATH")
    return ctx.run(["kitty", "--version"], mutating=False, check=False).out.strip()


def config_check(ctx: Ctx) -> Tuple[bool, str]:
    p = config_path(ctx)
    return p.is_file(), str(p)


def config_run(ctx: Ctx) -> str:
    dest = config_path(ctx)
    if dest.is_file():
        return f"already exists: {dest}"
    tpl = ctx.root / "dotfiles" / "kitty" / "kitty.conf"
    if not tpl.is_file():
        raise StepError(f"missing template: {tpl}")
    text = (tpl.read_text(encoding="utf-8")
           .replace("__ZSH__", ctx.which("zsh") or "/bin/zsh")
           .replace("__FONT_FAMILY__", HYPER_FONT_STACK.strip('"').split(",")[0].strip('"')))
    ctx.write_text(dest, text)
    return f"created {dest}"


def build() -> Module:
    S = Step
    return Module("kitty", "kitty terminal (trial)",
                  "Optional: install and configure kitty, to trial side by side with Hyper as a possible longer-term replacement.", [
        S("kitty-install", "Install kitty", "brew where available; apt/dnf package elsewhere; kitty's own installer script as a last resort. Ships its own (non-sixel) graphics protocol, on by default.",
          install_check, install_run, pm_sudo, unix_only, default=False),
        S("kitty-config", "kitty: config", "Create ~/.config/kitty/kitty.conf from dotfiles/kitty/kitty.conf (Nerd Font, zsh as the shell). Never overwrites an existing file. Local tweaks: ~/.kitty.local.conf.",
          config_check, config_run, supported=unix_only, default=False),
    ])
