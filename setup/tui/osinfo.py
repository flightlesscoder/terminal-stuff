"""OS / distro / package-manager detection."""
from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

EXTRA_PATHS = [
    "/home/linuxbrew/.linuxbrew/bin", "/opt/homebrew/bin", "/usr/local/bin",
    "~/.local/bin", "~/.cargo/bin",
]


def augment_path() -> None:
    """Add the usual non-default tool locations so we see what an interactive shell would."""
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for p in EXTRA_PATHS:
        p = os.path.expanduser(p)
        if os.path.isdir(p) and p not in parts:
            parts.append(p)
    os.environ["PATH"] = os.pathsep.join(parts)


@dataclass
class OsInfo:
    os: str                # linux | macos | windows | other
    distro: str            # bazzite, ubuntu, fedora, macos, ...
    version: str
    arch: str              # x86_64 | arm64 | ...
    immutable: bool        # ostree-based (Bazzite/Silverblue/Kinoite): no rpm layering by default
    wsl: bool
    pm: Optional[str]      # brew | apt | dnf | None

    def describe(self) -> str:
        extra = " immutable" if self.immutable else ""
        extra += " wsl" if self.wsl else ""
        return f"{self.os}/{self.distro} {self.version} {self.arch}{extra} pm={self.pm}"


def _os_release() -> dict:
    data = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                data[k] = v.strip().strip('"')
    except OSError:
        pass
    return data


def detect() -> OsInfo:
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(arch, arch)
    has = shutil.which
    if sys.platform == "darwin":
        return OsInfo("macos", "macos", platform.mac_ver()[0], arch, False, False,
                      "brew" if has("brew") else None)
    if sys.platform.startswith("linux"):
        rel = _os_release()
        distro = rel.get("ID", "linux")
        immutable = Path("/run/ostree-booted").exists()
        try:
            wsl = "microsoft" in Path("/proc/version").read_text().lower()
        except OSError:
            wsl = False
        if immutable:
            pm = "brew" if has("brew") else None     # don't layer rpms; brew/flatpak/distrobox instead
        elif has("apt-get"):
            pm = "apt"
        elif has("dnf"):
            pm = "dnf"
        elif has("brew"):
            pm = "brew"
        else:
            pm = None
        return OsInfo("linux", distro, rel.get("VERSION_ID", ""), arch, immutable, wsl, pm)
    if sys.platform in ("win32", "cygwin", "msys"):
        return OsInfo("windows", "windows", platform.version(), arch, False, False,
                      "winget" if has("winget") else None)
    return OsInfo("other", sys.platform, "", arch, False, False, None)
