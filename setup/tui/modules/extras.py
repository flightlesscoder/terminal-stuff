"""Module: extras -- lazygit, lazydocker, bottom, gdu, glow, zoxide, jq, Spotify."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import pkg_run, pm_sudo, unix_only
from .neovim import arch_tag  # reuse the same arch-tag-picker as nvim/tree-sitter installs

TOOLS_DIR = lambda ctx: ctx.home / ".local" / "share" / "terminal-stuff" / "tools"   # noqa: E731
LOCAL_BIN = lambda ctx: ctx.home / ".local" / "bin"                                  # noqa: E731


def which_check(cmd: str):
    def check(ctx: Ctx) -> Tuple[bool, str]:
        p = ctx.which(cmd)
        if not p:
            return False, f"{cmd} not found"
        ver = ctx.run([p, "--version"], mutating=False, check=False).out.splitlines()
        return True, f"{ver[0] if ver else '?'}  ({p})"
    return check


# ------------------------------------------------------------------ lazygit

def lazygit_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "lazygit"])
        if ctx.dry_run:
            return "would install lazygit"
    else:
        # apt doesn't ship lazygit at all without a third-party PPA; use upstream's own release
        # tarball on every Linux distro instead, same approach as nvim-install/treesitter-cli-install.
        release = ctx.fetch_json("https://api.github.com/repos/jesseduffield/lazygit/releases/latest")
        ver = release.get("tag_name", "").lstrip("v")
        tag = arch_tag(ctx, f"lazygit_{ver}_linux_x86_64.tar.gz", f"lazygit_{ver}_linux_arm64.tar.gz",
                       f"lazygit_{ver}_darwin_x86_64.tar.gz", f"lazygit_{ver}_darwin_arm64.tar.gz")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in lazygit release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install lazygit"
        dest = TOOLS_DIR(ctx) / f"lazygit-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        ctx.symlink(dest / "lazygit", LOCAL_BIN(ctx) / "lazygit")
    if not ctx.which("lazygit"):
        raise StepError(f"installed but not on PATH. Is {LOCAL_BIN(ctx)} on PATH?")
    return ctx.run(["lazygit", "--version"], mutating=False, check=False).out.splitlines()[0]


# ------------------------------------------------------------------ lazydocker

def lazydocker_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "lazydocker"])
        if ctx.dry_run:
            return "would install lazydocker"
    else:
        # Same situation as lazygit (same author, same release layout): no apt package.
        release = ctx.fetch_json("https://api.github.com/repos/jesseduffield/lazydocker/releases/latest")
        ver = release.get("tag_name", "").lstrip("v")
        tag = arch_tag(ctx, f"lazydocker_{ver}_Linux_x86_64.tar.gz", f"lazydocker_{ver}_Linux_arm64.tar.gz",
                       f"lazydocker_{ver}_Darwin_x86_64.tar.gz", f"lazydocker_{ver}_Darwin_arm64.tar.gz")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in lazydocker release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install lazydocker"
        dest = TOOLS_DIR(ctx) / f"lazydocker-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        ctx.symlink(dest / "lazydocker", LOCAL_BIN(ctx) / "lazydocker")
    if not ctx.which("lazydocker"):
        raise StepError(f"installed but not on PATH. Is {LOCAL_BIN(ctx)} on PATH?")
    return ctx.run(["lazydocker", "--version"], mutating=False, check=False).out.splitlines()[0]


# ------------------------------------------------------------------ zoxide

zoxide_run = pkg_run("zoxide", apt="zoxide", dnf="zoxide", brew="zoxide")


# ------------------------------------------------------------------ bottom

def bottom_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "bottom"])
        if ctx.dry_run:
            return "would install bottom"
    else:
        tag = arch_tag(ctx, "bottom_x86_64-unknown-linux-gnu.tar.gz", "bottom_aarch64-unknown-linux-gnu.tar.gz",
                       "bottom_x86_64-apple-darwin.tar.gz", "bottom_aarch64-apple-darwin.tar.gz")
        release = ctx.fetch_json("https://api.github.com/repos/ClementTsang/bottom/releases/latest")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in bottom release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install bottom"
        dest = TOOLS_DIR(ctx) / f"bottom-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        ctx.symlink(dest / "btm", LOCAL_BIN(ctx) / "btm")
    if not ctx.which("btm"):
        raise StepError(f"installed but not on PATH. Is {LOCAL_BIN(ctx)} on PATH?")
    return ctx.run(["btm", "--version"], mutating=False, check=False).out.splitlines()[0]


# ------------------------------------------------------------------ gdu

def gdu_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "gdu"])
        if ctx.dry_run:
            return "would install gdu"
    else:
        # gdu's own README just says "download the binary from the releases page" -- no apt/dnf
        # package -- so use upstream's release tarball on Linux too, same as lazygit/lazydocker.
        tag = arch_tag(ctx, "gdu_linux_amd64.tgz", "gdu_linux_arm64.tgz",
                       "gdu_darwin_amd64.tgz", "gdu_darwin_arm64.tgz")
        release = ctx.fetch_json("https://api.github.com/repos/dundee/gdu/releases/latest")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in gdu release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install gdu"
        dest = TOOLS_DIR(ctx) / f"gdu-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        binname = tag[:-len(".tgz")]                        # e.g. gdu_linux_amd64
        ctx.symlink(dest / binname, LOCAL_BIN(ctx) / "gdu")
    if not ctx.which("gdu"):
        raise StepError(f"installed but not on PATH. Is {LOCAL_BIN(ctx)} on PATH?")
    return ctx.run(["gdu", "--version"], mutating=False, check=False).out.splitlines()[0]


# ------------------------------------------------------------------ glow

def glow_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos" and ctx.which("brew"):
        ctx.run(["brew", "install", "glow"])
        if ctx.dry_run:
            return "would install glow"
    else:
        # charmbracelet's own release tarball, same situation as bottom/gdu (no apt/dnf package).
        release = ctx.fetch_json("https://api.github.com/repos/charmbracelet/glow/releases/latest")
        ver = release.get("tag_name", "").lstrip("v")
        tag = arch_tag(ctx, f"glow_{ver}_Linux_x86_64.tar.gz", f"glow_{ver}_Linux_arm64.tar.gz",
                       f"glow_{ver}_Darwin_x86_64.tar.gz", f"glow_{ver}_Darwin_arm64.tar.gz")
        asset = next((a for a in release.get("assets", []) if a["name"] == tag), None)
        if not asset:
            raise StepError(f"no '{tag}' asset in glow release {release.get('tag_name')}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if ctx.dry_run:
            return "would install glow"
        dest = TOOLS_DIR(ctx) / f"glow-{release.get('tag_name', 'latest')}"
        ctx.extract_archive(dl, dest)
        ctx.symlink(dest / "glow", LOCAL_BIN(ctx) / "glow")
    if not ctx.which("glow"):
        raise StepError(f"installed but not on PATH. Is {LOCAL_BIN(ctx)} on PATH?")
    return ctx.run(["glow", "--version"], mutating=False, check=False).out.splitlines()[0]


# ------------------------------------------------------------------ jq

jq_run = pkg_run("jq", apt="jq", dnf="jq", brew="jq")


# ------------------------------------------------------------------ Spotify (GUI app)

def _spotify_found(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.which("spotify")
    if p:
        return True, p
    if ctx.which("flatpak"):
        r = ctx.run(["flatpak", "info", "com.spotify.Client"], mutating=False, check=False)
        if r.rc == 0:
            return True, "flatpak: com.spotify.Client"
    for mac in ("/Applications/Spotify.app", str(ctx.home / "Applications/Spotify.app")):
        if Path(mac).exists():
            return True, mac
    return False, "not found"


def spotify_run(ctx: Ctx) -> str:
    if ctx.osinfo.os == "macos":
        if not ctx.which("brew"):
            raise StepError("Homebrew is required on macOS (https://brew.sh)")
        ctx.run(["brew", "install", "--cask", "spotify"])
    elif ctx.which("flatpak"):
        ctx.run(["flatpak", "install", "-y", "--noninteractive", "flathub", "com.spotify.Client"])
    elif ctx.osinfo.pm == "winget":
        ctx.run(["winget", "install", "-e", "--id", "Spotify.Spotify"])
    else:
        raise StepError("no install method available: install flatpak, or get Spotify from "
                        "https://www.spotify.com/download/linux/")
    if ctx.dry_run:
        return "would install Spotify"
    ok, detail = _spotify_found(ctx)
    if not ok:
        raise StepError("install command ran but Spotify still isn't detected")
    return detail


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("extras", "Extra CLI tools + Spotify",
                  "lazygit, lazydocker, bottom (btm), gdu, glow, zoxide, jq, and Spotify.", [
        S("lazygit-install", "Install lazygit", "Terminal UI for git. brew on macOS; upstream's release tarball on Linux (apt has no package without a third-party PPA). No sudo.",
          which_check("lazygit"), lazygit_run, supported=unix_only),
        S("lazydocker-install", "Install lazydocker", "Terminal UI for docker/docker-compose. brew on macOS; upstream's release tarball on Linux (same situation as lazygit: no apt package). No sudo.",
          which_check("lazydocker"), lazydocker_run, supported=unix_only),
        S("bottom-install", "Install bottom (btm)", "Graphical process/system monitor (top/htop alternative). brew on macOS; upstream's release tarball on Linux. No sudo.",
          which_check("btm"), bottom_run, supported=unix_only),
        S("gdu-install", "Install gdu", "Fast, interactive disk usage analyzer (windirstat-style: drill into directories, delete inline, mouse-clickable). brew on macOS; upstream's release tarball on Linux (no apt/dnf package). No sudo.",
          which_check("gdu"), gdu_run, supported=unix_only),
        S("glow-install", "Install glow", "Render/page markdown in the terminal (charmbracelet/glow). brew on macOS; upstream's release tarball on Linux (no apt/dnf package). No sudo.",
          which_check("glow"), glow_run, supported=unix_only),
        S("zoxide-install", "Install zoxide", "A faster `cd` that learns your most-used directories. Also needs a one-line init in your shell rc (zsh: eval \"$(zoxide init zsh)\") -- not added automatically since it's not yet wired into the zsh module.",
          which_check("zoxide"), zoxide_run, pm_sudo, unix_only),
        S("jq-install", "Install jq", "Command-line JSON processor.",
          which_check("jq"), jq_run, pm_sudo, unix_only),
        # No `supported=unix_only` here (unlike the others): spotify_run has real Windows/winget
        # logic, since this step (unlike the curses TUI) also runs fine via `setup.sh --run`
        # from Git Bash. It raises its own StepError when no install method is available.
        S("spotify-install", "Install Spotify", "flatpak (flathub) on Linux, brew cask on macOS, winget on Windows.",
          _spotify_found, spotify_run),
    ])
