"""Module: speech -- deploy ~/apps/scripts/speak-background.sh and confirm it's usable.

Ongoing configuration (voice/args, muted or not) is the hub app's Speech tab's job (SpeechTab.cs);
this module only creates the file once and verifies it's in a workable state. Never overwrites an
existing script, since it may have been customized since.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

from ..core import Ctx, Module, Step, StepError

SPEAK_LINE = '_speak_now "$TEXT" &'
ENGINE_ORDER = ("spd-say", "espeak-ng", "festival", "flite")     # matches detect_engine() in the script


def script_path(ctx: Ctx) -> Path:
    return ctx.home / "apps" / "scripts" / "speak-background.sh"


def template_path(ctx: Ctx) -> Path:
    return ctx.root / "dotfiles" / "scripts" / "speak-background.sh"


# ------------------------------------------------------------------ install

def install_check(ctx: Ctx) -> Tuple[bool, str]:
    p = script_path(ctx)
    return p.is_file(), str(p) if p.is_file() else f"{p} missing"


def install_run(ctx: Ctx) -> str:
    src = template_path(ctx)
    if not src.is_file():
        raise StepError(f"missing {src} (repo is broken?)")
    dest = script_path(ctx)
    if dest.is_file():
        return f"already exists: {dest}"
    ctx.write_text(dest, ctx.read_text(src), mode=0o755)
    return f"created {dest} from {src}"


# ------------------------------------------------------------------ verify

def detect_engine(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos":
        return "say"
    if ctx.osinfo.os == "windows" or ctx.which("powershell.exe") or ctx.which("pwsh"):
        if ctx.which("powershell.exe") or ctx.which("pwsh"):
            return "powershell"
    for e in ENGINE_ORDER:
        if ctx.which(e):
            return e
    return "none"


def probe(ctx: Ctx) -> Tuple[bool, str]:
    p = script_path(ctx)
    if not p.is_file():
        return False, f"{p} missing (run the 'speech-install' step)"
    if not (p.stat().st_mode & 0o111):
        return False, f"{p} exists but isn't executable"
    syn = ctx.run(["bash", "-n", str(p)], mutating=False, check=False)
    if syn.rc != 0:
        return False, f"script has a syntax error:\n{syn.out}"
    text = ctx.read_text(p)
    muted = re.search(rf"^\s*#\s*{re.escape(SPEAK_LINE)}", text, re.M) is not None
    unmuted = re.search(rf"^\s*{re.escape(SPEAK_LINE)}", text, re.M) is not None
    if not muted and not unmuted:
        return False, "SPEAK-LINE not found in the script; it may have been edited incompatibly"
    engine = detect_engine(ctx)
    if engine == "none":
        return False, "no speech engine found (install spd-say, espeak-ng, festival or flite)"
    detail = f"engine: {engine}, {'muted' if muted else 'unmuted'}"
    return True, detail


def verify_run(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (read-only check anyway)"
    ok, msg = probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("speech", "Speech (speak-background.sh)",
                  "Deploy ~/apps/scripts/speak-background.sh, a background text-to-speech script "
                  "(macOS say, or spd-say/espeak-ng/festival/flite on Linux, or PowerShell on Windows/WSL). "
                  "Configure voice/args and mute it from the hub app's Speech tab.", [
        S("speech-install", "Install speak-background.sh", "Copy dotfiles/scripts/speak-background.sh to ~/apps/scripts/speak-background.sh and make it executable. Never overwrites an existing file.",
          install_check, install_run),
        S("speech-verify", "Verify speak-background.sh", "Read-only: script exists, is executable, has no syntax errors, and a speech engine is available. Doesn't actually speak (that's the hub app's Test button).",
          probe, verify_run),
    ])
