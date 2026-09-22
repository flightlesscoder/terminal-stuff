"""Module: config -- ensure the layered JSONC config exists and is valid. See config/README.md."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .. import jsonc
from ..core import Ctx, Module, Step, StepError


def user_config_path(ctx: Ctx) -> Path:
    return ctx.home / ".config" / "terminal-stuff" / jsonc.CONFIG_FILENAME


def template_config_path(ctx: Ctx) -> Path:
    return ctx.root / "config" / "user-template.jsonc"


# ------------------------------------------------------------------ config-init

def init_check(ctx: Ctx) -> Tuple[bool, str]:
    p = user_config_path(ctx)
    return p.is_file(), str(p) if p.is_file() else f"{p} missing"


def init_run(ctx: Ctx) -> str:
    # Copies the (empty-arrays) template, NOT config/default.jsonc: default.jsonc's arrays are
    # already the base layer, and arrays extend across layers, so copying its contents here would
    # duplicate every entry rather than override anything -- see config/README.md.
    src = template_config_path(ctx)
    if not src.is_file():
        raise StepError(f"missing {src} (repo is broken?)")
    dest = user_config_path(ctx)
    if dest.is_file():
        return f"already exists: {dest}"
    ctx.write_text(dest, ctx.read_text(src))
    return f"created {dest} from {src}"


# ------------------------------------------------------------------ config-verify

def verify_probe(ctx: Ctx) -> Tuple[bool, str]:
    """Resolve the config the same way a tool run from the current directory would."""
    try:
        cfg, used = jsonc.resolve(ctx.root, Path.cwd(), ctx.home)
    except jsonc.JsoncError as e:
        return False, str(e)
    n_paths = len(cfg.get("paths", []))
    n_left = len(cfg.get("tmux", {}).get("statusLeft", []))
    n_right = len(cfg.get("tmux", {}).get("statusRight", []))
    layers = ", ".join(str(p) for p in used)
    return True, f"valid: {n_paths} paths, {n_left}+{n_right} tmux segments ({len(used)} layer(s): {layers})"


def verify_run(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (read-only check anyway)"
    ok, msg = verify_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("config", "Config (JSONC)",
                  "Ensure ~/.config/terminal-stuff/config.jsonc exists (from config/default.jsonc) and that "
                  "the layered config resolves cleanly. See config/README.md.", [
        S("config-init", "Create your config file", "Copy config/default.jsonc to ~/.config/terminal-stuff/config.jsonc if nothing is there yet. Never overwrites an existing file.",
          init_check, init_run),
        S("config-verify", "Verify config resolves", "Read-only: resolve default.jsonc + ~/.config/terminal-stuff/config.jsonc + ./.terminal-stuff.jsonc (from the current directory) and confirm the merged result parses.",
          verify_probe, verify_run),
    ])
