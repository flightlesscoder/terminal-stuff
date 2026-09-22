"""Module: neovim — nvim itself (a recent enough build), its treesitter/fuzzy-finder deps, and LazyVim.

Why LazyVim and not AstroNvim: both have a much bigger community than AstroNvim (14.4k stars/943
forks), but as of 2026-09 LazyVim (27.5k stars/1.8k forks) is the safer pick over NvChad (28.5k/2.2k,
edges LazyVim on raw stars) because NvChad's actual install repo, NvChad/starter, hadn't been pushed
in 14 months while LazyVim/starter was current within the last two weeks -- an installer nobody's
touched in over a year is a real risk for something this script re-clones on every fresh machine.
"""
from __future__ import annotations

import json
import platform
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import pkg_run, pm_sudo, unix_only

MIN_NVIM = (0, 11, 2)                    # LazyVim's minimum
MIN_TS = (0, 26, 1)                      # nvim-treesitter's minimum tree-sitter-cli
STARTER_URL = "https://github.com/LazyVim/starter"
LAZY_MARKER = "lua/config/lazy.lua"      # present in the starter; also what LazyVim itself creates
NVIM_HEADLESS_ENV = {"TERM": "xterm-256color"}
TOOLS_DIR = lambda ctx: ctx.home / ".local" / "share" / "terminal-stuff" / "tools"   # noqa: E731
LOCAL_BIN = lambda ctx: ctx.home / ".local" / "bin"                                  # noqa: E731

NVDIRS = ("nvim", "nvim-data")           # ~/.config, ~/.local/share|state|cache -> ~/.config/nvim etc.


# ------------------------------------------------------------------ helpers

def parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def arch_tag(ctx: Ctx, linux: str, linux_arm: str, mac: str, mac_arm: str) -> str:
    arm = ctx.osinfo.arch in ("arm64", "aarch64")
    if ctx.osinfo.os == "macos":
        return mac_arm if arm else mac
    return linux_arm if arm else linux


# ------------------------------------------------------------------ neovim itself

def nvim_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("nvim")
    if not p:
        return False, "nvim not found"
    ver = parse_version(ctx.run([p, "--version"], mutating=False, check=False).out)
    if ver is None:
        return False, f"found {p} but couldn't parse its version"
    ok = ver >= MIN_NVIM
    label = f"{'.'.join(map(str, ver))} ({p})"
    return ok, label if ok else f"{label} is older than the {'.'.join(map(str, MIN_NVIM))} LazyVim needs"


def nvim_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos":
        if not ctx.which("brew"):
            raise StepError("Homebrew is required on macOS (https://brew.sh)")
        ctx.run(["brew", "list", "--versions", "neovim"], mutating=False, check=False).out
        ctx.run(["brew", "install", "neovim"], check=False)
        ctx.run(["brew", "upgrade", "neovim"], check=False)          # no-op install if already current
        if ctx.dry_run:
            return "would install/upgrade neovim"
    else:
        # Distro packages (esp. apt) are frequently far too old for LazyVim; use upstream's own
        # prebuilt tarball instead, same approach as the Nerd Font/Hyper steps. No sudo needed.
        tag = arch_tag(ctx, "nvim-linux-x86_64.tar.gz", "nvim-linux-arm64.tar.gz", "", "")
        release = ctx.fetch_json("https://api.github.com/repos/neovim/neovim/releases/latest")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in neovim release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install/upgrade neovim"
        dest = TOOLS_DIR(ctx) / f"neovim-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        ctx.symlink(dest / "bin" / "nvim", LOCAL_BIN(ctx) / "nvim")
    ok, detail = nvim_check(ctx)
    if not ok:
        raise StepError(f"installed but still not new enough: {detail}. Is {LOCAL_BIN(ctx)} on PATH?")
    return f"nvim {detail}"


# ------------------------------------------------------------------ ripgrep / fd / tree-sitter-cli / cc

def rg_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("rg")
    return bool(p), p or "rg not found"


rg_run = pkg_run("rg", apt="ripgrep", dnf="ripgrep", brew="ripgrep")


def fd_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("fd") or ctx.which("fdfind")
    return bool(p), p or "fd not found"


def fd_run(ctx: Ctx) -> str:
    # Debian/Ubuntu's package is "fd-find" and installs the binary as "fdfind" (name clash avoidance),
    # so LazyVim's plain `fd` invocations would silently fail without a symlink.
    ctx.install_pkg(apt="fd-find", dnf="fd-find", brew="fd")
    if ctx.dry_run:
        return "would install fd"
    if ctx.which("fd"):
        return "installed fd"
    fdfind = ctx.which("fdfind")
    if not fdfind:
        raise StepError("package installed but neither 'fd' nor 'fdfind' is on PATH")
    ctx.symlink(Path(fdfind), LOCAL_BIN(ctx) / "fd")
    return f"installed fdfind, linked {LOCAL_BIN(ctx)}/fd -> it"


def ts_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("tree-sitter")
    if not p:
        return False, "tree-sitter not found"
    ver = parse_version(ctx.run([p, "--version"], mutating=False, check=False).out)
    ok = ver is not None and ver >= MIN_TS
    label = f"{'.'.join(map(str, ver))} ({p})" if ver else f"found {p} but couldn't parse its version"
    return ok, label


def ts_run(ctx: Ctx) -> str:
    # nvim-treesitter's README is explicit: install tree-sitter-cli via a package manager, "not npm".
    # apt/dnf don't reliably ship it, so use upstream's release zip (matches the neovim step's approach).
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "tree-sitter"])
        if ctx.dry_run:
            return "would install tree-sitter-cli"
    else:
        tag = arch_tag(ctx, "tree-sitter-cli-linux-x64.zip", "tree-sitter-cli-linux-arm64.zip",
                       "tree-sitter-cli-macos-x64.zip", "tree-sitter-cli-macos-arm64.zip")
        release = ctx.fetch_json("https://api.github.com/repos/tree-sitter/tree-sitter/releases/latest")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in tree-sitter release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install tree-sitter-cli"
        dest = TOOLS_DIR(ctx) / f"tree-sitter-cli-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        exe = dest / "tree-sitter"
        if exe.exists():
            exe.chmod(exe.stat().st_mode | 0o111)
        ctx.symlink(exe, LOCAL_BIN(ctx) / "tree-sitter")
    ok, detail = ts_check(ctx)
    if not ok:
        raise StepError(f"installed but not usable: {detail}. Is {LOCAL_BIN(ctx)} on PATH?")
    return f"tree-sitter {detail}"


def cc_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("cc") or ctx.which("gcc") or ctx.which("clang")
    return bool(p), p or "no C compiler (cc/gcc/clang) found"


def cc_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos":
        raise StepError("no C compiler found. Run `xcode-select --install` yourself (it needs the GUI "
                        "installer) and re-run this step to verify")
    ctx.install_pkg(apt="build-essential", dnf="gcc", brew="gcc")   # brew: Bazzite (Linux, pm=brew), not real macOS
    if ctx.dry_run:
        return "would install a C compiler"
    ok, detail = cc_check(ctx)
    if not ok:
        raise StepError("installed a compiler package but still can't find cc/gcc/clang on PATH")
    return detail


# ------------------------------------------------------------------ LazyVim config

def config_dir(ctx: Ctx) -> Path:
    return ctx.home / ".config" / "nvim"


def lock_path(ctx: Ctx) -> Path:
    return config_dir(ctx) / "lazy-lock.json"


def config_check(ctx: Ctx) -> Tuple[bool, str]:
    marker = config_dir(ctx) / LAZY_MARKER
    if marker.is_file():
        return True, str(config_dir(ctx))
    if config_dir(ctx).exists() and any(config_dir(ctx).iterdir()):
        return False, f"{config_dir(ctx)} exists (not LazyVim) and will be backed up"
    return False, f"{config_dir(ctx)} missing"


def config_run(ctx: Ctx) -> str:
    marker = config_dir(ctx) / LAZY_MARKER
    if marker.is_file():
        return f"already installed: {config_dir(ctx)}"
    if not ctx.which("git"):
        raise StepError("git is required (see setup/doctor.sh)")

    # Official instructions (https://lazyvim.org/installation): back up ~/.config/nvim (required)
    # plus the data/state/cache dirs (recommended) before cloning the starter over them.
    import time
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backed_up = []
    for base, name in ((ctx.home / ".config", "nvim"), (ctx.home / ".local" / "share", "nvim"),
                       (ctx.home / ".local" / "state", "nvim"), (ctx.home / ".cache", "nvim")):
        src = base / name
        if src.exists() or src.is_symlink():
            dst = base / f"{name}.bak-{stamp}"
            ctx.run(["mv", src, dst])
            backed_up.append(str(dst))

    ctx.git_clone(STARTER_URL, config_dir(ctx))
    git_dir = config_dir(ctx) / ".git"
    if git_dir.exists():
        # Upstream's own advice, so people can put the config under their own repo (or nvim-plugins/) later.
        ctx.run(["rm", "-rf", git_dir])

    if ctx.dry_run:
        return "would install the LazyVim starter config"
    note = f"; backed up: {', '.join(backed_up)}" if backed_up else ""
    return f"cloned the LazyVim starter into {config_dir(ctx)}{note}"


# ------------------------------------------------------------------ plugin sync

def lock_summary(ctx: Ctx) -> Tuple[int, bool]:
    """(plugin count, has 'LazyVim' entry) from lazy-lock.json, or (0, False) if absent/unreadable."""
    try:
        data = json.loads(ctx.read_text(lock_path(ctx)) or "{}")
    except json.JSONDecodeError:
        return 0, False
    return len(data), "LazyVim" in data


def plugins_check(ctx: Ctx) -> Tuple[bool, str]:
    n, has_lazyvim = lock_summary(ctx)
    if n == 0:
        return False, "no plugins installed yet"
    if not has_lazyvim:
        return False, f"lazy-lock.json has {n} entries but no 'LazyVim' one; looks unexpected"
    return True, f"{n} plugins locked (lazy-lock.json)"


def plugins_run(ctx: Ctx) -> str:
    marker = config_dir(ctx) / LAZY_MARKER
    if not marker.is_file() and not ctx.dry_run:
        raise StepError("LazyVim isn't installed yet; run the 'lazyvim-config' step first")
    ok, _ = nvim_check(ctx)
    if not ok and not ctx.dry_run:
        raise StepError("nvim doesn't meet LazyVim's version requirement; run the 'nvim-install' step first")
    # Headless first start: this is what bootstraps lazy.nvim and installs every plugin (network-heavy,
    # can easily take a few minutes -- including compiling treesitter parsers with the C compiler).
    res = ctx.run(["nvim", "--headless", "-u", str(config_dir(ctx) / "init.lua"),
                  "+Lazy! sync", "+qa"], env=NVIM_HEADLESS_ENV, check=False, timeout=1800)
    if ctx.dry_run:
        return "would run a headless plugin sync"
    n, has_lazyvim = lock_summary(ctx)
    if n == 0 or not has_lazyvim:
        tail = "\n".join(res.out.splitlines()[-15:])
        raise StepError(f"sync finished but lazy-lock.json doesn't look right (see the log)\n{tail}")
    return f"{n} plugins installed/updated"


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("neovim", "Neovim + LazyVim",
                  "A recent-enough neovim (upstream build if the distro package is too old), ripgrep/fd/"
                  "tree-sitter-cli/a C compiler, and the LazyVim starter config with its plugins synced.", [
        S("nvim-install", "Install/upgrade neovim", f"Ensure nvim >= {'.'.join(map(str, MIN_NVIM))} (LazyVim's minimum). brew on macOS; upstream's prebuilt tarball into ~/.local/share/terminal-stuff (symlinked from ~/.local/bin) on Linux, since apt/dnf are often too old. No sudo.",
          nvim_check, nvim_run, supported=unix_only),
        S("ripgrep-install", "Install ripgrep", "For LazyVim's live grep.",
          rg_check, rg_run, pm_sudo, unix_only),
        S("fd-install", "Install fd", "For LazyVim's file finder. On Debian/Ubuntu the package installs as 'fdfind'; this symlinks ~/.local/bin/fd to it.",
          fd_check, fd_run, pm_sudo, unix_only),
        S("cc-install", "Install a C compiler", "cc/gcc/clang, needed by nvim-treesitter to compile parsers. On macOS this only checks, since Xcode Command Line Tools need the GUI installer (`xcode-select --install`).",
          cc_check, cc_run, pm_sudo, unix_only),
        S("treesitter-cli-install", "Install tree-sitter-cli", f"nvim-treesitter now requires the real tree-sitter-cli (>= {'.'.join(map(str, MIN_TS))}), not npm's package. brew on macOS; upstream's release zip on Linux (same approach as nvim-install). No sudo.",
          ts_check, ts_run, pm_sudo, unix_only),
        S("lazyvim-config", "Install LazyVim (config)",
          "Clone the LazyVim starter (github.com/LazyVim/starter) into ~/.config/nvim. Backs up an existing "
          "~/.config/nvim (required) and ~/.local/share|state/nvim, ~/.cache/nvim (recommended) to "
          "<dir>.bak-<date-time> first, per LazyVim's own install instructions. Removes the clone's .git "
          "(also per those instructions) so you can put it under version control yourself later.",
          config_check, config_run, supported=unix_only),
        S("lazyvim-plugins", "Sync LazyVim plugins",
          "Headless `nvim +Lazy! sync`: bootstraps lazy.nvim and installs/updates every plugin (network, can take minutes). "
          "Shows done once lazy-lock.json is populated; safe to re-run any time to update.",
          plugins_check, plugins_run, supported=unix_only),
    ])
