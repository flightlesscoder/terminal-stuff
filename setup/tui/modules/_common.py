"""Helpers shared by setup modules."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Optional, Tuple

from ..core import Ctx, StepError

pm_sudo = lambda ctx: ctx.osinfo.pm in ("apt", "dnf")      # noqa: E731
ZSHRC = lambda ctx: ctx.home / ".zshrc"                    # noqa: E731


def unix_only(ctx: Ctx) -> Optional[str]:
    if ctx.osinfo.os not in ("linux", "macos"):
        return "Linux/macOS only (on Windows use WSL)"
    return None


def windows_only(ctx: Ctx) -> Optional[str]:
    if ctx.osinfo.os != "windows":
        return "Windows only (Linux/macOS/WSL use tj/n instead -- see the node-n-install step)"
    return None


def source_line(path: Path) -> str:
    q = shlex.quote(str(path))
    return f"[ -r {q} ] && source {q}"


def zsh_block(name: str, dotfile: str):
    """(check, run) pair for a managed ~/.zshrc block that sources dotfiles/zsh/<dotfile>."""
    def body(ctx: Ctx) -> str:
        return source_line(ctx.root / "dotfiles" / "zsh" / dotfile)

    def check(ctx: Ctx) -> Tuple[bool, str]:
        return ctx.block_current(ZSHRC(ctx), name, body(ctx)), "~/.zshrc block"

    def run(ctx: Ctx) -> str:
        src = ctx.root / "dotfiles" / "zsh" / dotfile
        if not src.is_file():
            raise StepError(f"missing dotfile in repo: {src}")
        changed = ctx.ensure_block(ZSHRC(ctx), name, body(ctx))
        return "updated ~/.zshrc" if changed else "~/.zshrc already up to date"
    return check, run


def which_check(cmd: str):
    def check(ctx: Ctx) -> Tuple[bool, str]:
        p = ctx.which(cmd)
        return bool(p), p or f"{cmd} not found"
    return check


def pkg_run(cmd: str, **names):
    def run(ctx: Ctx) -> str:
        ctx.install_pkg(**names)
        if not ctx.dry_run and not ctx.which(cmd):
            raise StepError(f"package installed but '{cmd}' is still not on PATH")
        return f"installed {cmd}"
    return run


def clone_step(url: str, dest_of, marker: str):
    def check(ctx: Ctx) -> Tuple[bool, str]:
        d = dest_of(ctx)
        return (d / marker).exists(), str(d)

    def run(ctx: Ctx) -> str:
        d = dest_of(ctx)
        if (d / marker).exists():
            return f"already present: {d}"
        if d.exists() and any(d.iterdir()):
            raise StepError(f"{d} exists but doesn't look like the expected checkout; move it away")
        ctx.git_clone(url, d)
        return f"cloned into {d}"
    return check, run
