"""Module: hub — build the Terminal Stuff Hub TUI (apps/hub) and add it to the tmux-which-key menu."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import pm_sudo, unix_only
from .tmux import conf_path, private_server, tpm_dir

MIN_SDK_MAJOR = 10                       # Terminal.Gui 2.5 targets net10.0
MENU_NAME = "Terminal Stuff Hub"
MENU_KEY = "h"                           # free at the root of which-key's default menu
WINDOW_NAME = "hub"
BLOCK = "hub"
DOTNET_ENV = {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1"}


def app_dir(ctx: Ctx) -> Path:
    return ctx.root / "apps" / "hub"


def dll(ctx: Ctx) -> Path:
    return app_dir(ctx) / "bin" / "hub.dll"


def launcher(ctx: Ctx) -> Path:
    return app_dir(ctx) / "hub"


def wk_dir(ctx: Ctx) -> Path:
    return tpm_dir(ctx).parent / "tmux-which-key"


def wk_config(ctx: Ctx) -> Path:
    return wk_dir(ctx) / "config.yaml"


# ------------------------------------------------------------------ dotnet SDK

def sdk_major(ctx: Ctx) -> Optional[int]:
    if not ctx.which("dotnet"):
        return None
    out = ctx.run(["dotnet", "--list-sdks"], mutating=False, check=False, env=DOTNET_ENV).out
    majors = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", out, re.M)]
    return max(majors) if majors else None


def dotnet_check(ctx: Ctx) -> Tuple[bool, str]:
    major = sdk_major(ctx)
    if major is None:
        return False, "no .NET SDK found"
    return major >= MIN_SDK_MAJOR, f".NET SDK {major} (need >= {MIN_SDK_MAJOR})"


def dotnet_run(ctx: Ctx) -> str:
    ctx.install_pkg(apt=f"dotnet-sdk-{MIN_SDK_MAJOR}.0", dnf=f"dotnet-sdk-{MIN_SDK_MAJOR}.0", brew="dotnet")
    if ctx.dry_run:
        return f"would install the .NET {MIN_SDK_MAJOR} SDK"
    major = sdk_major(ctx)
    if major is None or major < MIN_SDK_MAJOR:
        raise StepError(f".NET SDK {MIN_SDK_MAJOR}+ still not available after install (found: {major}). "
                        f"Install it with Microsoft's script: curl -sSL https://dot.net/v1/dotnet-install.sh | "
                        f"bash -s -- --channel {MIN_SDK_MAJOR}.0")
    return f".NET SDK {major} available"


# ------------------------------------------------------------------ build

def read_stamp(ctx: Ctx) -> Optional[Dict[str, str]]:
    """Ask the built app for its stamp (`hub.dll --about` prints key: value lines)."""
    if not dll(ctx).is_file() or not ctx.which("dotnet"):
        return None
    res = ctx.run(["dotnet", dll(ctx), "--about"], mutating=False, check=False, env=DOTNET_ENV, timeout=60)
    stamp = {}
    for line in res.out.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            stamp[k.strip()] = v.strip()
    return stamp if res.rc == 0 and "commit" in stamp else None


def head_commit(ctx: Ctx) -> str:
    if not ctx.which("git"):
        return "none"
    out = ctx.run(["git", "-C", ctx.root, "rev-parse", "--short=12", "HEAD"], mutating=False, check=False).out.strip()
    return out if re.fullmatch(r"[0-9a-f]{7,40}", out) else "none"


def build_check(ctx: Ctx) -> Tuple[bool, str]:
    stamp = read_stamp(ctx)
    if stamp is None:
        return False, "not built yet"
    head = head_commit(ctx)
    if stamp["commit"] != head:
        return False, f"built from {stamp['commit']} but HEAD is {head} (rebuild)"
    sources = list(app_dir(ctx).glob("*.cs")) + list(app_dir(ctx).glob("*.csproj"))
    if sources and max(p.stat().st_mtime for p in sources) > dll(ctx).stat().st_mtime:
        return False, "sources changed since the last build (rebuild)"
    return True, f"built {stamp.get('built', '?')} from {stamp['commit']}" + (" (+uncommitted changes)" if stamp.get("dirty") == "true" else "")


def build_run(ctx: Ctx) -> str:
    if not ctx.which("dotnet"):
        raise StepError("dotnet is not installed; run the 'hub-dotnet' step first")
    ctx.run(["dotnet", "build", app_dir(ctx) / "hub.csproj", "-c", "Release", "-o", app_dir(ctx) / "bin",
             "--nologo", "-v", "minimal"], env=DOTNET_ENV, timeout=1800)
    if ctx.dry_run:
        return "would build apps/hub"
    stamp = read_stamp(ctx)
    if stamp is None:
        raise StepError("build finished but `hub.dll --about` doesn't work; see the log")
    return f"built {stamp.get('built', '?')} from commit {stamp['commit']}" + (" (with uncommitted changes)" if stamp.get("dirty") == "true" else "")


# ------------------------------------------------------------------ which-key menu entry

def menu_body(ctx: Ctx) -> str:
    path = str(launcher(ctx))
    if re.search(r"""["'\\$`\n]""", path):
        raise StepError(f"the repo path contains a quote, backslash or $, which the menu entry can't quote safely: {path}")
    # new-window -S reuses an existing 'hub' window instead of opening a second one
    return (f"  - name: {MENU_NAME}\n"
            f"    key: {MENU_KEY}\n"
            f"    command: 'new-window -S -n {WINDOW_NAME} \"{path}\"'")


def root_keys(text: str) -> Dict[str, str]:
    """{key: item name} for the root of `items:`, ignoring our own block."""
    begin, end = f"# >>> terminal-stuff:{BLOCK} >>>", f"# <<< terminal-stuff:{BLOCK} <<<"
    keys: Dict[str, str] = {}
    in_items = skipping = False
    name = ""
    for line in text.splitlines():
        if line.startswith("items:"):
            in_items = True
            continue
        if not in_items:
            continue
        if begin in line:
            skipping = True
        elif end in line:
            skipping = False
            continue
        if skipping:
            continue
        m = re.match(r"^  - name:\s*(.*)$", line)
        if m:
            name = m.group(1).strip().strip("'\"")
        k = re.match(r"^    key:\s*(.*)$", line)
        if k:
            keys[k.group(1).strip().strip("'\"")] = name
    return keys


def menu_check(ctx: Ctx) -> Tuple[bool, str]:
    if not wk_dir(ctx).is_dir():
        return False, "tmux-which-key isn't installed (run the 'tmux' module first)"
    if not wk_config(ctx).exists():
        return False, "which-key config not created yet"
    return ctx.block_current(wk_config(ctx), BLOCK, menu_body(ctx)), f"entry '{MENU_NAME}' (key {MENU_KEY}) in which-key config"


def menu_run(ctx: Ctx) -> str:
    wk, cfg = wk_dir(ctx), wk_config(ctx)
    if not wk.is_dir():
        raise StepError("tmux-which-key isn't installed; run the 'tmux' module (tmux-plugins step) first")
    body = menu_body(ctx)
    if not cfg.exists():
        example = wk / "config.example.yaml"
        if not example.is_file():
            raise StepError(f"{example} is missing; reinstall the plugin")
        ctx.write_text(cfg, ctx.read_text(example))         # same first-run copy the plugin itself does
    text = ctx.read_text(cfg)
    if "items:" not in text:
        raise StepError(f"{cfg} has no top-level `items:` list")
    after = text.split("\nitems:", 1)[-1]
    if re.search(r"^[A-Za-z_][\w-]*:", after, re.M):
        raise StepError("`items:` isn't the last top-level key of the which-key config, so the entry can't be "
                        f"appended safely. Move `items:` to the end of {cfg} (or add the entry by hand).")
    taken = root_keys(text).get(MENU_KEY)
    if taken:
        raise StepError(f"which-key root key '{MENU_KEY}' is already used by '{taken}'; change MENU_KEY in "
                        "setup/tui/modules/hub.py")
    changed = ctx.ensure_block(cfg, BLOCK, body)
    build = wk / "plugin" / "build.py"
    if ctx.which("python3") and build.is_file():
        ctx.run(["python3", build, cfg, wk / "plugin" / "init.tmux"])   # regenerate the menu file now
    note = "" if not changed else "; press prefix + r (or restart tmux) to load it into a running tmux"
    return ("added" if changed else "already had") + f" '{MENU_NAME}' (key {MENU_KEY}) in the which-key menu" + note


# ------------------------------------------------------------------ verification

def hub_probe(ctx: Ctx, deep: bool) -> Tuple[bool, str]:
    """Static: app answers --about, launcher is executable, a private tmux builds the which-key menu with
    our entry. Deep: additionally run the menu's exact command in that tmux and confirm the app draws."""
    if not launcher(ctx).is_file() or not launcher(ctx).stat().st_mode & 0o111:
        return False, f"{launcher(ctx)} is missing or not executable"
    stamp = read_stamp(ctx)
    if stamp is None:
        return False, "the app isn't built (or `hub.dll --about` fails); run the 'hub-build' step"
    if not ctx.which("tmux") or not wk_dir(ctx).is_dir():
        return False, "tmux and tmux-which-key are needed (run the 'tmux' module)"
    if "terminal-stuff:tmux" not in ctx.read_text(conf_path(ctx)):
        return False, "~/.tmux.conf doesn't source our config (run the tmux module)"
    if not ctx.block_current(wk_config(ctx), BLOCK, menu_body(ctx)):
        return False, "the which-key config has no (current) hub entry; run the 'hub-menu' step"
    problems = []
    with private_server(ctx) as env:
        base = ["tmux"]
        q = lambda *a: ctx.run(base + list(a), mutating=False, check=False, env=env, timeout=30).out  # noqa: E731
        ctx.run(base + ["-f", str(conf_path(ctx)), "new-session", "-d", "-s", "verify"], mutating=False, env=env, timeout=60)
        init = wk_dir(ctx) / "plugin" / "init.tmux"
        for _ in range(10):                                     # the plugin rebuilds init.tmux at startup
            if str(launcher(ctx)) in ctx.read_text(init):
                break
            time.sleep(1)
        built = ctx.read_text(init)
        if MENU_NAME not in built or str(launcher(ctx)) not in built:
            problems.append("the which-key menu built at tmux startup doesn't contain the hub entry")
        if deep and not problems:
            q("new-window", "-S", "-n", WINDOW_NAME, str(launcher(ctx)))
            screen = ""
            for _ in range(15):                                 # dotnet startup takes a moment
                screen = q("capture-pane", "-p", "-t", WINDOW_NAME)
                if "Built" in screen and "Commit" in screen:
                    break
                time.sleep(1)
            ctx.log.info("hub window screen:\n%s", screen)
            if not ("Built" in screen and "Commit" in screen):
                problems.append("the app opened from the menu command but its About screen never appeared (see log)")
            q("send-keys", "-t", WINDOW_NAME, "Escape")
    if problems:
        return False, "hub isn't wired up correctly:\n  - " + "\n  - ".join(problems)
    return True, (f"menu entry present and app starts (built from {stamp['commit']})" if deep
                  else f"menu entry present in the built which-key menu; app built from {stamp['commit']}")


def hub_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (nothing was actually changed)"
    ok, msg = hub_probe(ctx, deep=True)
    if not ok:
        raise StepError(msg)
    return msg


def hub_verify_check(ctx: Ctx) -> Tuple[bool, str]:
    ok, msg = hub_probe(ctx, deep=False)
    return ok, msg.splitlines()[0]


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("hub", "Terminal Stuff Hub (apps/hub TUI + tmux menu entry)",
                  f"A tabbed, mouse-enabled TUI in apps/hub (C#/.NET, Terminal.Gui) and a '{MENU_NAME}' entry (key {MENU_KEY}) in the tmux-which-key menu.", [
        S("hub-dotnet", f"Install the .NET {MIN_SDK_MAJOR} SDK", f"Needed to build apps/hub (Terminal.Gui 2.5 targets .NET {MIN_SDK_MAJOR}). Skipped if a new enough SDK is present.",
          dotnet_check, dotnet_run, pm_sudo, unix_only),
        S("hub-build", "Build the hub app", "dotnet build apps/hub into apps/hub/bin. Stamps the build time and git commit shown on the About tab. Shows 'todo' again when HEAD or the sources move on.",
          build_check, build_run, supported=unix_only),
        S("hub-menu", "tmux-which-key: add hub menu entry", f"Append a marked block to which-key's config.yaml adding '{MENU_NAME}' (prefix + Space, {MENU_KEY}), which opens the app in a tmux window. Needs the tmux module's plugins.",
          menu_check, menu_run, supported=unix_only),
        S("hub-verify", "Verify hub + menu entry", "Boot a throwaway tmux server (private socket), confirm the built which-key menu has the entry, and run the menu's command to see the app's About screen. Read-only.",
          hub_verify_check, hub_verify, supported=unix_only),
    ])
