"""Module: node -- tj/n (Node version manager) on Linux/macOS/WSL, nvm-windows on native Windows.

n isn't supported on native Windows (not even Git Bash -- see its README), so that's the one
"context tj/n doesn't support" among our target platforms; nvm-windows fills in there instead.
N_PREFIX/NPM_CONFIG_PREFIX + the PATH wiring live in dotfiles/zsh/node.zsh (zsh-only, so unix_only
here too -- nvm-windows manages its own PATH/env via the Windows installer, no zshrc involved).
"""
from __future__ import annotations

from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import unix_only, windows_only, zsh_block

N_PREFIX = lambda ctx: ctx.home / "apps" / "n-prefix"          # noqa: E731
N_BIN = lambda ctx: N_PREFIX(ctx) / "bin"                      # noqa: E731
NPM_PREFIX = lambda ctx: ctx.home / "apps" / "npm-prefix"      # noqa: E731
N_SCRIPT_URL = "https://raw.githubusercontent.com/tj/n/master/bin/n"
NVM_WINDOWS_WINGET_ID = "CoreyButler.NVMforWindows"


# ------------------------------------------------------------------ n (install the script itself)

def n_check(ctx: Ctx) -> Tuple[bool, str]:
    p = N_BIN(ctx) / "n"
    return p.is_file(), str(p)


def n_run(ctx: Ctx) -> str:
    dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / "n"
    ctx.download(N_SCRIPT_URL, dl)
    if ctx.dry_run:
        return "would install n"
    ctx.mkdir(N_BIN(ctx))
    dest = N_BIN(ctx) / "n"
    ctx.run(["install", "-m", "755", dl, dest])
    if not dest.is_file():
        raise StepError(f"install ran but {dest} is missing")
    return f"installed n into {dest}"


# ------------------------------------------------------------------ node (bootstrap an LTS version via n)

def node_lts_check(ctx: Ctx) -> Tuple[bool, str]:
    node_bin = N_BIN(ctx) / "node"
    if not node_bin.is_file():
        return False, "no active node version (run the 'node-lts-install' step)"
    out = ctx.run([str(node_bin), "--version"], mutating=False, check=False).out.strip()
    return bool(out), out or "node present but --version failed"


def node_lts_run(ctx: Ctx) -> str:
    n_bin = N_BIN(ctx) / "n"
    if not n_bin.is_file() and not ctx.dry_run:
        raise StepError("n is not installed; run the 'node-n-install' step first")
    ctx.run([str(n_bin), "lts"], env={"N_PREFIX": str(N_PREFIX(ctx))})
    if ctx.dry_run:
        return "would install the latest Node.js LTS via n"
    out = ctx.run([str(N_BIN(ctx) / "node"), "--version"], mutating=False, check=False).out.strip()
    if not out:
        raise StepError("n lts ran but node --version failed afterward")
    return f"node {out} active (via n)"


# ------------------------------------------------------------------ zshrc: env vars + PATH

def env_run(ctx: Ctx, inner_run) -> str:
    ctx.mkdir(N_BIN(ctx))
    ctx.mkdir(NPM_PREFIX(ctx) / "bin")
    return inner_run(ctx)


# ------------------------------------------------------------------ nvm-windows (native Windows only)

def nvm_windows_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("nvm")
    return bool(p), p or "nvm not found"


def nvm_windows_run(ctx: Ctx) -> str:
    if not ctx.which("winget"):
        raise StepError("winget is required (Windows Package Manager -- comes with modern Windows 10/11)")
    ctx.run(["winget", "install", "-e", "--id", NVM_WINDOWS_WINGET_ID,
             "--accept-source-agreements", "--accept-package-agreements"])
    if ctx.dry_run:
        return "would install nvm-windows"
    if not ctx.which("nvm"):
        raise StepError("winget install ran but 'nvm' still isn't on PATH; open a new shell and re-check")
    return "installed nvm-windows"


# ------------------------------------------------------------------ verification

def node_probe(ctx: Ctx) -> Tuple[bool, str]:
    """Read-only: node + npm actually resolve and run, from wherever this platform puts them."""
    if ctx.osinfo.os == "windows":
        p = ctx.which("nvm")
        if not p:
            return False, "nvm-windows not found (run the 'node-nvm-windows-install' step)"
        return True, f"nvm-windows: {p} (run 'nvm install lts' then 'nvm use <version>' to get node/npm)"
    n_bin = N_BIN(ctx) / "n"
    if not n_bin.is_file():
        return False, "n is not installed (run the 'node-n-install' step)"
    node_bin, npm_bin = N_BIN(ctx) / "node", N_BIN(ctx) / "npm"
    if not node_bin.is_file():
        return False, "no active node version (run the 'node-lts-install' step)"
    node_ver = ctx.run([str(node_bin), "--version"], mutating=False, check=False).out.strip()
    npm_ver = ctx.run([str(npm_bin), "--version"], mutating=False, check=False).out.strip() if npm_bin.is_file() else ""
    if not node_ver or not npm_ver:
        return False, f"node ({node_ver or 'MISSING'}) / npm ({npm_ver or 'MISSING'}) not both working"
    return True, f"node {node_ver}, npm {npm_ver} (via n, N_PREFIX={N_PREFIX(ctx)})"


def node_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (nothing was actually changed)"
    ok, msg = node_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


# ------------------------------------------------------------------ module

def build() -> Module:
    env_c, env_r_inner = zsh_block("node-env", "node.zsh")
    S = Step
    return Module("node", "Node.js version management (tj/n)",
                  "tj/n for Node version management (nvm-windows on native Windows), with N_PREFIX/"
                  "NPM_CONFIG_PREFIX under ~/apps/ and PATH wiring in ~/.zshrc.", [
        S("node-n-install", "Install tj/n", "Download the n script (github.com/tj/n) straight into "
          "$N_PREFIX/bin -- no npm bootstrap needed. Not supported on native Windows (use nvm-windows instead).",
          n_check, n_run, supported=unix_only),
        S("node-lts-install", "Install Node.js LTS (via n)", "Run `n lts` to download and activate the "
          "latest Node.js LTS release. Needs the 'node-n-install' step first.",
          node_lts_check, node_lts_run, supported=unix_only),
        S("node-env", "zshrc: node env + PATH", "Managed ~/.zshrc block: export N_PREFIX ($HOME/apps/n-prefix) "
          "and NPM_CONFIG_PREFIX ($HOME/apps/npm-prefix), and put n-prefix/bin, n-prefix, npm-prefix/bin and "
          "npm-prefix on PATH. Creates both directories.",
          env_c, lambda ctx: env_run(ctx, env_r_inner), supported=unix_only),
        S("node-nvm-windows-install", "Install nvm-windows", "coreybutler/nvm-windows via winget -- tj/n "
          "doesn't support native Windows (not even Git Bash), so this is the fallback there.",
          nvm_windows_check, nvm_windows_run, supported=windows_only),
        S("node-verify", "Verify node/npm work", "Confirm node and npm actually run from wherever this "
          "platform's install puts them (n's $N_PREFIX/bin, or nvm-windows). Read-only.",
          lambda ctx: node_probe(ctx), node_verify),
    ])
