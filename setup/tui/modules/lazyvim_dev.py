"""Module: lazyvim-dev -- language tooling on top of the neovim/LazyVim module, for React/TS/
modern JS, C#, PowerShell, Python, Bash and SQL.

LazyVim ships official "extras" (LSP + treesitter + formatter/linter, one `:LazyExtras` toggle)
for typescript, json, python, dotnet (C#) and sql -- enabled here by editing the state file
LazyVim itself reads (~/.config/nvim/lazyvim.json), so it works headlessly, no editor UI needed.
Bash and PowerShell have NO official extra (checked the actual repo listing, not guessing --
lua/lazyvim/plugins/extras/lang/ has no bash.lua or powershell.lua); those get a small custom
plugin spec instead (dotfiles/nvim/extra-langs.lua), the exact pattern LazyVim's own extras use.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import pkg_run, pm_sudo, unix_only
from .neovim import NVIM_HEADLESS_ENV, config_dir, lock_summary

# Official LazyVim extras covering: React/TS/modern JS, JSON (package.json/tsconfig), Python,
# C# (dotnet), SQL. Exact names confirmed against github.com/LazyVim/LazyVim's
# lua/lazyvim/plugins/extras/lang/ listing, not guessed.
EXTRAS = [
    "lazyvim.plugins.extras.lang.typescript",
    "lazyvim.plugins.extras.lang.json",
    "lazyvim.plugins.extras.lang.python",
    "lazyvim.plugins.extras.lang.dotnet",
    "lazyvim.plugins.extras.lang.sql",
]
# lazyvim.json's own schema version (lua/lazyvim/config/init.lua: M.json.version). MUST be written
# whenever we touch this file: with no "version" key, LazyVim treats it as the ancient v0 format
# and "migrates" it by prepending "lazyvim.plugins.extras." to every entry -- which, applied to our
# already-fully-qualified names, doubles the prefix and breaks every one of them. Confirmed by
# actually hitting that exact failure the first time and reading json.lua's migrate() function
# rather than guessing; if a future LazyVim bumps this, the version stays as-is (LazyVim upgrades
# its own state on next load, which is a no-op for us -- we're not writing anything version-specific).
LAZYVIM_JSON_VERSION = 8
EXTRA_LANGS_FILE = "extra-langs.lua"                  # dotfiles/nvim/<this> -> lua/plugins/<this>
DADBOD_FILE = "dadbod-connections.lua"                # same deploy pattern
MASON_TOOLS = ("bash-language-server", "powershell-editor-services")


def lazyvim_json_path(ctx: Ctx) -> Path:
    return config_dir(ctx) / "lazyvim.json"


# ------------------------------------------------------------------ prerequisite runtimes

def langtools_check(ctx: Ctx) -> Tuple[bool, str]:
    missing = [c for c in ("node", "npm", "pwsh") if not ctx.which(c)]
    return not missing, "node, npm, pwsh all present" if not missing else f"missing: {', '.join(missing)}"


def langtools_run(ctx: Ctx) -> str:
    # node/npm: needed at runtime by vtsls (TypeScript) and friends, from the lang.typescript extra.
    # pwsh: needed at runtime by powershell_es (it's a PowerShell script mason downloads, not a
    # standalone binary) -- and it's the natural PowerShell tool for this environment generally.
    if ctx.osinfo.pm == "brew" and ctx.which("brew"):
        ctx.run(["brew", "install", "node"], check=False)
        ctx.run(["brew", "install", "powershell"], check=False)
    elif ctx.osinfo.pm in ("apt", "dnf"):
        ctx.install_pkg(apt="nodejs", dnf="nodejs")
        if not ctx.which("pwsh"):
            raise StepError("node installed, but PowerShell isn't in the default apt/dnf repos -- "
                            "install it from Microsoft's own instructions: "
                            "https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-linux")
    else:
        raise StepError("no supported package manager (brew/apt/dnf) to install node/PowerShell")
    if ctx.dry_run:
        return "would install node + PowerShell"
    ok, detail = langtools_check(ctx)
    if not ok:
        raise StepError(f"install ran but still {detail}")
    return detail


# ------------------------------------------------------------------ LazyVim extras (lazyvim.json)

def extras_check(ctx: Ctx) -> Tuple[bool, str]:
    p = lazyvim_json_path(ctx)
    if not config_dir(ctx).is_dir():
        return False, "~/.config/nvim missing (run the neovim module's 'lazyvim-config' step first)"
    # lazyvim.json itself isn't created by cloning the starter or even a plugin sync -- LazyVim
    # only ever writes it lazily, the first time something (e.g. :LazyExtras) changes the extras
    # list. Its absence just means "zero extras enabled so far", not a broken/incomplete install.
    if not p.is_file():
        return False, "missing: " + ", ".join(e.rsplit(".", 1)[-1] for e in EXTRAS)
    try:
        data = json.loads(ctx.read_text(p) or "{}")
    except json.JSONDecodeError as e:
        return False, f"{p} isn't valid JSON: {e}"
    have = set(data.get("extras", []))
    missing = [e for e in EXTRAS if e not in have]
    return not missing, "all enabled" if not missing else f"missing: {', '.join(e.rsplit('.', 1)[-1] for e in missing)}"


def extras_run(ctx: Ctx) -> str:
    if not config_dir(ctx).is_dir():
        raise StepError("~/.config/nvim missing; run the neovim module's 'lazyvim-config' step first")
    p = lazyvim_json_path(ctx)
    try:
        data = json.loads(ctx.read_text(p) or "{}")
    except json.JSONDecodeError as e:
        raise StepError(f"{p} isn't valid JSON: {e}") from e
    have = list(data.get("extras", []))
    added = [e for e in EXTRAS if e not in have]
    data["extras"] = have + added
    data.setdefault("version", LAZYVIM_JSON_VERSION)     # see LAZYVIM_JSON_VERSION's comment
    changed = ctx.write_text(p, json.dumps(data, indent=2) + "\n")
    if ctx.dry_run:
        return f"would enable: {', '.join(added) or '(none needed)'}"
    return f"enabled {len(added)} extra(s): {', '.join(a.rsplit('.', 1)[-1] for a in added)}" if changed else "already all enabled"


# ------------------------------------------------------------------ plugin-spec deployment
# (bash/powershell LSPs, dadbod connections: both are "copy dotfiles/nvim/X.lua to
# ~/.config/nvim/lua/plugins/X.lua once, never touch it again" -- same shape, one factory.)

def plugin_spec_step(filename: str):
    def path(ctx: Ctx) -> Path:
        return config_dir(ctx) / "lua" / "plugins" / filename

    def check(ctx: Ctx) -> Tuple[bool, str]:
        p = path(ctx)
        return p.is_file(), str(p)

    def run(ctx: Ctx) -> str:
        dest = path(ctx)
        if dest.is_file():
            return f"already exists: {dest}"
        src = ctx.root / "dotfiles" / "nvim" / filename
        if not src.is_file():
            raise StepError(f"missing template: {src}")
        ctx.write_text(dest, ctx.read_text(src))
        return f"created {dest}"
    return check, run


# ------------------------------------------------------------------ sync (installs everything above)

def sync_check(ctx: Ctx) -> Tuple[bool, str]:
    mason = ctx.home / ".local" / "share" / "nvim" / "mason" / "packages"
    missing_tools = [t for t in MASON_TOOLS if not (mason / t).is_dir()]
    n, has_lazyvim = lock_summary(ctx)
    if n == 0:
        return False, "plugins not synced yet"
    if missing_tools:
        return False, f"mason tools missing: {', '.join(missing_tools)}"
    return True, f"{n} plugins, mason tools present"


def sync_run(ctx: Ctx) -> str:
    if not (config_dir(ctx) / "lua" / "plugins" / EXTRA_LANGS_FILE).is_file() and not ctx.dry_run:
        raise StepError("run the 'lazyvim-extra-langs' step first")
    # Two separate nvim invocations, not one with both commands: newly-installed plugins' opts()
    # (which is what feeds mason-tool-installer's ensure_installed -- e.g. lang.sql's own sqlfluff
    # entry, not just ours) aren't necessarily fully merged yet in the same process that just ran
    # `+Lazy! sync`, so a mason install immediately after can race and abort mid-download. Hit this
    # for real (sqlfluff got cut off) before splitting it into two clean startups fixed it.
    ctx.run(["nvim", "--headless", "-u", str(config_dir(ctx) / "init.lua"), "+Lazy! sync", "+qa"],
            env=NVIM_HEADLESS_ENV, check=False, timeout=1800)
    # NOT `+MasonToolsInstallSync`: despite the name, it returns near-instantly under --headless
    # (confirmed: ~0.03s, then mason logs "Neovim exited while packages were still installing" and
    # aborts them) -- headless mode doesn't pump the event loop the way its internal wait expects.
    # A plain `vim.wait()` does pump it for real, so that's what actually blocks for the installs.
    res = ctx.run(["nvim", "--headless", "-u", str(config_dir(ctx) / "init.lua"), "+MasonToolsInstall",
                  "-c", "lua vim.wait(45000, function() return false end, 500)", "+qa"],
                  env=NVIM_HEADLESS_ENV, check=False, timeout=1800)
    if ctx.dry_run:
        return "would sync plugins + mason tools"
    ok, detail = sync_check(ctx)
    if not ok:
        tail = "\n".join(res.out.splitlines()[-15:])
        raise StepError(f"sync finished but {detail} (see the log)\n{tail}")
    return detail


# ------------------------------------------------------------------ module

def build() -> Module:
    extra_langs_check, extra_langs_run = plugin_spec_step(EXTRA_LANGS_FILE)
    dadbod_check, dadbod_run = plugin_spec_step(DADBOD_FILE)
    S = Step
    return Module("lazyvim-dev", "LazyVim: dev languages",
                  "React/TypeScript/modern JS, C#, PowerShell, Python, Bash, SQL -- on top of the "
                  "neovim module's LazyVim install.", [
        S("lazyvim-langtools", "Install node + PowerShell", "Runtimes the LSPs below need: node/npm (vtsls and friends) and pwsh (powershell_es is a PowerShell script, not a standalone binary). brew where available.",
          langtools_check, langtools_run, pm_sudo, unix_only),
        S("lazyvim-extras", "Enable LazyVim lang extras", "typescript, json, python, dotnet (C#), sql -- edits ~/.config/nvim/lazyvim.json's extras list directly (same thing :LazyExtras writes), so it works headlessly. sql pulls in vim-dadbod + vim-dadbod-ui automatically -- LazyVim's own official answer for database support (checked: no separate community extra needed).",
          extras_check, extras_run, supported=unix_only),
        S("lazyvim-extra-langs", "Add Bash + PowerShell LSPs", "Neither has an official LazyVim extra. Deploys dotfiles/nvim/extra-langs.lua to ~/.config/nvim/lua/plugins/ (bashls + powershell_es via a plain custom plugin spec). Never overwrites an existing file.",
          extra_langs_check, extra_langs_run, supported=unix_only),
        S("lazyvim-dadbod", "Add dadbod connection template", "Deploys dotfiles/nvim/dadbod-connections.lua to ~/.config/nvim/lua/plugins/ -- a vim.g.dbs template with commented-out example URLs for MSSQL, Azure SQL, Postgres and MongoDB (use $ENV_VAR for passwords, never literal ones). Fill in your real connections there; that file lives outside this repo, so it's never at risk of becoming public. Never overwrites an existing file.",
          dadbod_check, dadbod_run, supported=unix_only),
        S("lazyvim-dev-sync", "Sync plugins + LSP tools", "Headless `nvim +Lazy! sync +MasonToolsInstallSync`: installs the new extras' plugins and every LSP/formatter they need, including bash-language-server and powershell-editor-services. Network, can take a few minutes.",
          sync_check, sync_run, supported=unix_only),
    ])
