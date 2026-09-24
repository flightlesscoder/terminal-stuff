"""Module: ai-agents -- the pi coding agent, its packages, and terminal-stuff's own MCP server.

Opt-in: every step is `default=False`, so nothing here is pre-selected in the TUI or run by a bare
`--run ai-agents`; pick the steps (or the module) deliberately.

Pieces:
  - pi itself (npm: @earendil-works/pi-coding-agent) and the pi packages/plugins listed in PI_PACKAGES
    (installed with `pi install`, which records them in ~/.pi/agent/settings.json).
  - Private pi extensions (custom model providers/adapters) live in ./local/pi-custom/ -- git-ignored,
    never pushed -- and get symlinked into ~/.pi/agent/extensions/.
  - apps/mcp-server (Node): a pluggable MCP server. Its `npm install`, and an entry for it in pi's
    MCP config (~/.pi/agent/mcp.json, read by the pi-mcp-adapter package). Which tool plugins it
    loads is config (`mcp.enabledPlugins`), edited from the hub app's MCP Server tab.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import unix_only

PI_NPM_PACKAGE = "@earendil-works/pi-coding-agent"
# Sources as `pi install` takes them. pi-mcp-adapter is what lets pi talk to MCP servers at all.
# (A machine-specific local-path relay for pi-web is deliberately not listed.)
PI_PACKAGES = ("npm:pi-web-access", "npm:@ff-labs/pi-fff", "npm:pi-goal-x", "npm:pi-vcc",
               "npm:pi-mcp-adapter", "npm:@giladbarnea/pi-time-sense")
MCP_SERVER_NAME = "terminal-stuff"


def agent_dir(ctx: Ctx) -> Path:
    return Path(os.environ.get("PI_CODING_AGENT_DIR") or ctx.home / ".pi" / "agent")


def server_dir(ctx: Ctx) -> Path:
    return ctx.root / "apps" / "mcp-server"


def custom_dir(ctx: Ctx) -> Path:
    return ctx.root / "local" / "pi-custom"


def _read_json(ctx: Ctx, path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(ctx.read_text(path))
    except json.JSONDecodeError as e:
        raise StepError(f"{path} isn't valid JSON ({e}); fix or move it, then re-run")
    if not isinstance(data, dict):
        raise StepError(f"{path}: top level must be a JSON object")
    return data


# ------------------------------------------------------------------ pi itself

def pi_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("pi")
    if not p:
        return False, "pi not found"
    ver = ctx.run([p, "--version"], mutating=False, check=False).out.strip()
    return True, f"{p} ({ver or 'version unknown'})"


def pi_run(ctx: Ctx) -> str:
    if not ctx.which("npm"):
        raise StepError("npm not found; run the 'node' module first (or install Node.js)")
    ctx.run(["npm", "install", "-g", PI_NPM_PACKAGE])
    if ctx.dry_run:
        return "would install pi"
    if not ctx.which("pi"):
        raise StepError("npm install ran but 'pi' is still not on PATH (check `npm prefix -g`/bin is on PATH)")
    return f"installed {PI_NPM_PACKAGE}"


# ------------------------------------------------------------------ pi packages

def _installed_packages(ctx: Ctx) -> list:
    pk = _read_json(ctx, agent_dir(ctx) / "settings.json").get("packages", [])
    return [p if isinstance(p, str) else p.get("source", "") for p in pk] if isinstance(pk, list) else []


def packages_check(ctx: Ctx) -> Tuple[bool, str]:
    have = _installed_packages(ctx)
    missing = [p for p in PI_PACKAGES if p not in have]
    if missing:
        return False, f"{len(missing)}/{len(PI_PACKAGES)} missing: {', '.join(missing)}"
    return True, f"{len(PI_PACKAGES)} pi packages installed"


def packages_run(ctx: Ctx) -> str:
    pi = ctx.which("pi")
    if not pi and not ctx.dry_run:
        raise StepError("pi isn't installed; run the 'pi-install' step first")
    have = _installed_packages(ctx)
    todo = [p for p in PI_PACKAGES if p not in have]
    for pkg in todo:
        ctx.run([pi or "pi", "install", pkg], timeout=600)
    return f"installed: {', '.join(todo)}" if todo else "all pi packages already installed"


# ------------------------------------------------------------------ private extensions (local/pi-custom)

def _custom_files(ctx: Ctx) -> list:
    d = custom_dir(ctx)
    return sorted(d.glob("*.ts")) if d.is_dir() else []


def custom_check(ctx: Ctx) -> Tuple[bool, str]:
    files = _custom_files(ctx)
    if not files:
        return True, f"nothing in {custom_dir(ctx)} (private extensions go there; git-ignored)"
    ext = agent_dir(ctx) / "extensions"
    bad = [f.name for f in files if os.path.realpath(ext / f.name) != os.path.realpath(f)]
    return (not bad), (f"{len(files)} linked into {ext}" if not bad else f"not linked: {', '.join(bad)}")


def custom_run(ctx: Ctx) -> str:
    files = _custom_files(ctx)
    if not files:
        return f"nothing to link ({custom_dir(ctx)} has no .ts files)"
    ext = agent_dir(ctx) / "extensions"
    changed = [f.name for f in files if ctx.symlink(f, ext / f.name)]
    return f"linked: {', '.join(changed)}" if changed else "already linked"


# ------------------------------------------------------------------ terminal-stuff MCP server

def server_deps_check(ctx: Ctx) -> Tuple[bool, str]:
    sdk = server_dir(ctx) / "node_modules" / "@modelcontextprotocol" / "sdk"
    return sdk.is_dir(), str(server_dir(ctx)) if sdk.is_dir() else "npm dependencies not installed"


def server_deps_run(ctx: Ctx) -> str:
    if not ctx.which("npm"):
        raise StepError("npm not found; run the 'node' module first (or install Node.js)")
    ctx.run(["npm", "install", "--no-audit", "--no-fund"], cwd=server_dir(ctx))
    return f"installed dependencies in {server_dir(ctx)}"


def _wanted_entry(ctx: Ctx) -> dict:
    return {"command": ctx.which("node") or "node", "args": [str(server_dir(ctx) / "server.mjs")],
            "directTools": True}


def wire_check(ctx: Ctx) -> Tuple[bool, str]:
    path = agent_dir(ctx) / "mcp.json"
    have = (_read_json(ctx, path).get("mcpServers") or {}).get(MCP_SERVER_NAME)
    if not have:
        return False, f"no '{MCP_SERVER_NAME}' entry in {path}"
    want = _wanted_entry(ctx)
    if have.get("args") != want["args"]:
        return False, f"'{MCP_SERVER_NAME}' in {path} points at {have.get('args')}, not this repo"
    return True, f"{path} -> {want['args'][0]}"


def wire_run(ctx: Ctx) -> str:
    path = agent_dir(ctx) / "mcp.json"
    data = _read_json(ctx, path)            # merge into whatever's there; never touch other servers
    servers = data.setdefault("mcpServers", {})
    current = servers.get(MCP_SERVER_NAME) or {}
    servers[MCP_SERVER_NAME] = {**current, **_wanted_entry(ctx)}
    ctx.write_text(path, json.dumps(data, indent=2) + "\n")   # write_text backs up an existing file
    return f"registered '{MCP_SERVER_NAME}' in {path}"


# ------------------------------------------------------------------ verification

def probe(ctx: Ctx) -> Tuple[bool, str]:
    checks = [("pi", pi_check(ctx)[0]), ("pi packages", packages_check(ctx)[0]),
              ("private extensions", custom_check(ctx)[0]), ("MCP server deps", server_deps_check(ctx)[0]),
              ("MCP server wired into pi", wire_check(ctx)[0])]
    bad = [label for label, ok in checks if not ok]
    if bad:
        return False, "not fully set up: " + ", ".join(bad)
    node = ctx.which("node")
    out = ctx.run([node or "node", str(server_dir(ctx) / "server.mjs"), "--list-plugins"],
                  mutating=False, check=False)
    try:
        plugins = json.loads(out.out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, f"MCP server didn't answer --list-plugins:\n{out.out}"
    on = [p["name"] for p in plugins if p.get("enabled")]
    return True, f"pi + MCP server ready; enabled plugins: {', '.join(on) or '(none)'}"


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
    return Module("ai-agents", "AI agent tools (pi + MCP server)",
                  "Opt-in. The pi coding agent with your pi packages, private pi extensions from ./local/pi-custom, "
                  "and terminal-stuff's own pluggable MCP server (apps/mcp-server) wired into pi. Choose which MCP "
                  "tool plugins load from the hub app's MCP Server tab.", [
        S("pi-install", "Install pi coding agent", f"npm install -g {PI_NPM_PACKAGE}. Needs Node.js/npm (see the node module).",
          pi_check, pi_run, supported=unix_only, default=False),
        S("pi-packages", "Install pi packages", "pi install each of: " + ", ".join(PI_PACKAGES) +
          " (recorded in ~/.pi/agent/settings.json). Skips ones already listed.",
          packages_check, packages_run, supported=unix_only, default=False),
        S("pi-custom-extensions", "Link private pi extensions", "Symlink each ./local/pi-custom/*.ts (git-ignored: custom "
          "model providers/adapters) into ~/.pi/agent/extensions/. Nothing to do if the folder is empty.",
          custom_check, custom_run, supported=unix_only, default=False),
        S("mcp-server-install", "Install MCP server dependencies", "npm install in apps/mcp-server.",
          server_deps_check, server_deps_run, supported=unix_only, default=False),
        S("mcp-pi-wire", "Register MCP server with pi", "Add a 'terminal-stuff' entry (with directTools) to pi's "
          "~/.pi/agent/mcp.json, preserving any other servers. Needs the pi-mcp-adapter package (in pi-packages).",
          wire_check, wire_run, supported=unix_only, default=False),
        S("ai-agents-verify", "Verify AI agent tools", "Read-only: pi, its packages, private extensions, MCP server "
          "deps and pi wiring are in place, and the server lists its enabled plugins.",
          probe, verify_run, supported=unix_only, default=False),
    ])
