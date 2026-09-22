"""Entry point: TUI by default; --list / --run for scripting and testing."""
from __future__ import annotations

import argparse
import json as jsonlib
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

from . import logsetup
from .core import Ctx, Module, Step, StepState, check_step, run_steps
from .modules import load_all
from .osinfo import augment_path, detect

ROOT = Path(__file__).resolve().parents[2]


def parse(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="setup.sh", description="Interactive setup for this environment.")
    p.add_argument("--list", action="store_true", help="list modules/steps with their current state and exit")
    p.add_argument("--json", action="store_true", help="with --list: machine-readable JSON; with --run: JSON-lines events on stdout (used by the hub app's Setup tab)")
    p.add_argument("--run", metavar="MODULE", help="run a module without the TUI")
    p.add_argument("--steps", metavar="ID,ID", help="with --run: only these steps (default: those not yet done)")
    p.add_argument("--all", action="store_true", help="with --run: every supported step, even if done")
    p.add_argument("-n", "--dry-run", action="store_true", help="log what would happen; change nothing")
    p.add_argument("-y", "--yes", action="store_true", help="with --run: don't ask for confirmation")
    return p.parse_args(argv)


def log_environment(ctx: Ctx, args: argparse.Namespace) -> None:
    log = ctx.log
    log.info("terminal-stuff setup starting; argv=%s", sys.argv[1:])
    log.info("repo root: %s", ctx.root)
    log.info("os: %s", ctx.osinfo.describe())
    log.info("python %s (%s) on %s", platform.python_version(), sys.executable, platform.platform())
    log.info("user=%s uid=%s home=%s", os.environ.get("USER", "?"), os.geteuid(), ctx.home)
    for k in ("SHELL", "TERM", "LANG", "XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY", "HOME", "PATH"):
        log.info("env %s=%s", k, os.environ.get(k, ""))
    for tool in ("git", "zsh", "tmux", "fzf", "brew", "curl", "sudo"):
        p = ctx.which(tool)
        if p:
            try:
                out = subprocess.run([p, "--version"], stdin=subprocess.DEVNULL, capture_output=True,
                                     text=True, timeout=20).stdout.splitlines()
                log.info("tool %-5s %s  [%s]", tool, p, out[0] if out else "")
            except Exception as e:                        # noqa: BLE001
                log.info("tool %-5s %s  [version check failed: %s]", tool, p, e)
        else:
            log.info("tool %-5s (not found)", tool)


def default_selection(states: dict, module: Module) -> List[Step]:
    return [s for s in module.steps
            if states[(module.id, s.id)].kind in ("todo", "unknown") and s.default]


def compute_states(ctx: Ctx, modules: List[Module]) -> dict:
    return {(m.id, s.id): check_step(ctx, s) for m in modules for s in m.steps}


ICON = {"done": "✔", "todo": "·", "unsupported": "-", "unknown": "?"}


def cmd_list(ctx: Ctx, modules: List[Module], as_json: bool = False) -> int:
    states = compute_states(ctx, modules)
    if as_json:
        doc = {
            "os": ctx.osinfo.describe(),
            "log": ctx.log.handlers[0].baseFilename,        # type: ignore[attr-defined]
            "modules": [
                {
                    "id": m.id, "title": m.title, "description": m.description,
                    "steps": [
                        {"id": s.id, "title": s.title, "description": s.description,
                         "needs_sudo": bool(s.needs_sudo(ctx)), "default": s.default,
                         "state": states[(m.id, s.id)].kind, "detail": states[(m.id, s.id)].detail}
                        for s in m.steps
                    ],
                }
                for m in modules
            ],
        }
        print(jsonlib.dumps(doc))
        return 0
    print(f"system: {ctx.osinfo.describe()}")
    for m in modules:
        print(f"\n{m.id} — {m.title}")
        for s in m.steps:
            st: StepState = states[(m.id, s.id)]
            print(f"  {ICON[st.kind]} {s.id:<16} {st.kind:<11} {s.title}" + (f"  [{st.detail}]" if st.detail else ""))
    print(f"\nlog: {ctx.log.handlers[0].baseFilename}")     # type: ignore[attr-defined]
    return 0


def cmd_run(ctx: Ctx, modules: List[Module], args: argparse.Namespace) -> int:
    mod = next((m for m in modules if m.id == args.run), None)
    if mod is None:
        print(f"unknown module '{args.run}'. available: {', '.join(m.id for m in modules)}", file=sys.stderr)
        return 2
    states = compute_states(ctx, modules)
    if args.steps:
        ids = [x.strip() for x in args.steps.split(",") if x.strip()]
        unknown = [i for i in ids if i not in {s.id for s in mod.steps}]
        if unknown:
            print(f"unknown step(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        chosen = [s for s in mod.steps if s.id in ids]
    elif args.all:
        chosen = [s for s in mod.steps if states[(mod.id, s.id)].kind != "unsupported"]
    else:
        chosen = default_selection(states, mod)
    if not chosen:
        if args.json:
            print(jsonlib.dumps({"event": "summary", "ok": 0, "failed": 0, "skipped": 0, "nothing_to_do": True}))
        else:
            print("nothing to do.")
        return 0
    as_json = args.json
    if not as_json:
        print(f"{'DRY RUN: ' if ctx.dry_run else ''}{mod.id}: {len(chosen)} step(s)")
        for s in chosen:
            print(f"  - {s.id}: {s.title}")
    if not args.yes and not as_json:
        if input("proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("aborted.")
            return 1
    if any(s.needs_sudo(ctx) for s in chosen) and not ctx.dry_run and os.geteuid() != 0:
        if subprocess.call(["sudo", "-v"]) != 0:
            msg = "sudo authentication failed"
            print(jsonlib.dumps({"event": "error", "message": msg}) if as_json else msg, file=sys.stderr)
            return 1

    if as_json:
        def emit(obj: dict) -> None:
            print(jsonlib.dumps(obj), flush=True)
        ctx.sink = lambda line: emit({"event": "output", "line": line})

        def on_event(kind, m, s, res):
            if kind == "start":
                emit({"event": "start", "module": m.id, "step": s.id, "title": s.title})
            else:
                emit({"event": "end", "module": m.id, "step": s.id, "status": res.status, "detail": res.detail})
    else:
        ctx.sink = lambda line: print("    " + line)

        def on_event(kind, m, s, res):
            if kind == "start":
                print(f"\n==> {s.id}: {s.title}")
            else:
                print(f"    [{res.status}] {res.detail}" if res.detail else f"    [{res.status}]")

    results = run_steps(ctx, [(mod, s) for s in chosen], on_event)
    if as_json:
        failed = [r for r in results if r.status == "failed"]
        print(jsonlib.dumps({
            "event": "summary", "ok": sum(r.status == "ok" for r in results), "failed": len(failed),
            "skipped": sum(r.status == "skipped" for r in results),
            "log": ctx.log.handlers[0].baseFilename,        # type: ignore[attr-defined]
        }), flush=True)
        return 1 if failed else 0
    return summarize(ctx, results)


def summarize_lines(ctx: Ctx, results) -> List[str]:
    failed = [r for r in results if r.status == "failed"]
    lines = [f"{sum(r.status == 'ok' for r in results)} ok, {len(failed)} failed, "
             f"{sum(r.status == 'skipped' for r in results)} skipped"
             f"{' (dry-run: nothing was changed)' if ctx.dry_run else ''}", ""]
    for r in sorted(results, key=lambda r: r.status != "failed"):     # failures first
        first = r.detail.splitlines()[0] if r.detail else ""
        lines.append(f"{'FAILED' if r.status == 'failed' else r.status:<7} {r.step}: {first}")
        if r.status == "failed":
            lines += [f"          {ln}" for ln in r.detail.splitlines()[1:6]]
    lines += ["", f"log: {ctx.log.handlers[0].baseFilename}"]      # type: ignore[attr-defined]
    return lines


def summarize(ctx: Ctx, results) -> int:
    print()
    print("\n".join(summarize_lines(ctx, results)))
    return 1 if any(r.status == "failed" for r in results) else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse(argv)
    augment_path()
    log, log_path = logsetup.init(ROOT, console=False)
    try:
        ctx = Ctx(ROOT, detect(), log, dry_run=args.dry_run)
        log_environment(ctx, args)
        modules = load_all()
        if args.list:
            return cmd_list(ctx, modules, as_json=args.json)
        if args.run:
            return cmd_run(ctx, modules, args)
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("not a terminal; use --list or --run MODULE", file=sys.stderr)
            return 2
        try:
            from .ui import App
        except ImportError as e:
            print(f"the TUI needs Python's curses module ({e}); use --list / --run instead", file=sys.stderr)
            return 1
        return App(ctx, modules).run()
    except KeyboardInterrupt:
        log.error("interrupted by user")
        return 130
    except Exception:                                     # noqa: BLE001
        log.critical("unhandled exception:\n%s", traceback.format_exc())
        print(f"unexpected error; see {log_path}", file=sys.stderr)
        return 1
    finally:
        log.info("exit")
        logsetup.prune(ROOT / "logs", keep_prefix=log_path.stem)
