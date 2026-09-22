"""Module: terminal environment — zsh, oh-my-zsh, pure, fzf, Nerd Font, Hyper (tmux lives in modules/tmux.py)."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Optional, Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import ZSHRC, clone_step, pkg_run, pm_sudo, unix_only, which_check, zsh_block

OMZ_DIR = lambda ctx: ctx.home / ".oh-my-zsh"              # noqa: E731
PURE_DIR = lambda ctx: ctx.home / ".zsh" / "pure"          # noqa: E731
SCM_BREEZE_DIR = lambda ctx: ctx.home / ".scm_breeze"      # noqa: E731
HYPER_APPIMAGE = lambda ctx: ctx.home / "Applications" / "Hyper.AppImage"   # noqa: E731

# ------------------------------------------------------------------ scm_breeze
#
# scm_breeze.sh has no built-in "disable everything" env var (checked its source: the only knob,
# SCM_BREEZE_DISABLE_ASSETS_MANAGEMENT, just skips its design/repo-index assets, not the git
# aliases/keybindings). So instead of relying on a flag scm_breeze itself doesn't have, the
# managed zshrc block (dotfiles/zsh/scm_breeze.zsh) wraps the `source .../scm_breeze.sh` line
# itself in `[ -z "$CLAUDECODE" ]` -- skip loading it at all inside a Claude Code session, since
# its git wrapper/keybindings can error out (something around its safe-eval helpers) when Claude
# shells out to git, not just when a human types at the prompt. We deliberately don't run
# scm_breeze's own install.sh (it unconditionally appends an unwrapped, unguarded source line to
# ~/.zshrc via plain `>>`, outside our marker system -- that would both duplicate our managed
# block's source line and defeat the CLAUDECODE guard); we replicate only the two things that
# matter (the ~/.scmbrc / ~/.git.scmbrc config files, copied from its example templates the same
# way its own `_create_or_patch_scmbrc` does) ourselves via Ctx.


def scm_breeze_config_check(ctx: Ctx) -> Tuple[bool, str]:
    missing = [n for n in (".scmbrc", ".git.scmbrc") if not (ctx.home / n).is_file()]
    return not missing, "~/.scmbrc, ~/.git.scmbrc" if not missing else f"missing: {', '.join(missing)}"


def scm_breeze_config_run(ctx: Ctx) -> str:
    d = SCM_BREEZE_DIR(ctx)
    if not (d / "scm_breeze.sh").exists() and not ctx.dry_run:
        raise StepError("scm_breeze is not cloned; run the 'scm-breeze-install' step first")
    made = []
    for name, example in ((".scmbrc", "scmbrc.example"), (".git.scmbrc", "git.scmbrc.example")):
        dest = ctx.home / name
        if dest.exists():
            continue
        if ctx.dry_run:
            made.append(name)
            continue
        src = d / example
        if not src.is_file():
            raise StepError(f"missing template in scm_breeze checkout: {src}")
        ctx.write_text(dest, src.read_text(encoding="utf-8"))
        made.append(name)
    return f"created {', '.join(made)}" if made else "~/.scmbrc, ~/.git.scmbrc already present"


# ------------------------------------------------------------------ chsh (actual login shell)
#
# Separate from -- and opt-in unlike -- zsh-env: tmux's default-shell (see dotfiles/tmux/
# set-default-shell.sh) and most terminal emulators fall back to $SHELL / the passwd-database
# login shell when they don't override it themselves. Hit for real: the account's shell was still
# /bin/bash even with zsh fully configured everywhere else. This step is the actual root fix, but
# it changes system account state (not just files under $HOME), so it's default=False -- opt in
# deliberately, don't bundle it into "select everything".

def current_username() -> str:
    import pwd                                       # unix-only; import lazily (module is imported on Windows too)
    return pwd.getpwuid(os.getuid()).pw_name


def login_shell_check(ctx: Ctx) -> Tuple[bool, str]:
    import pwd
    zsh = ctx.which("zsh")
    if not zsh:
        return False, "zsh is not installed (run the 'zsh-install' step first)"
    try:
        current = pwd.getpwnam(current_username()).pw_shell
    except KeyError:
        return False, "could not read the account's shell from the passwd database"
    if os.path.realpath(current) == os.path.realpath(zsh):
        return True, current
    return False, f"login shell is {current}, not {zsh}"


def login_shell_run(ctx: Ctx) -> str:
    zsh = ctx.which("zsh")
    if not zsh and not ctx.dry_run:
        raise StepError("zsh is not installed; run the 'zsh-install' step first")
    user = current_username()
    shells_path = Path("/etc/shells")
    shells = [ln.strip() for ln in ctx.read_text(shells_path).splitlines()]
    if zsh and zsh not in shells:
        if ctx.dry_run:
            ctx.info(f"[dry-run] would add {zsh} to /etc/shells")
        else:
            ctx.run(["sh", "-c", f"echo {shlex.quote(zsh)} >> /etc/shells"], sudo=True)
    ctx.run(["chsh", "-s", zsh, user], sudo=True)
    if ctx.dry_run:
        return f"would set the login shell to {zsh}"
    ok, detail = login_shell_check(ctx)
    if not ok:
        raise StepError(f"chsh ran but the account's shell still isn't zsh ({detail})")
    return f"login shell is now {zsh} (takes effect on your next login -- open a new terminal/tmux/SSH session)"


# ------------------------------------------------------------------ helpers


# ------------------------------------------------------------------ fzf verification

def fzf_probe(ctx: Ctx, timeout: int = 60) -> Tuple[bool, str]:
    """Read-only: start an interactive zsh with the real ~/.zshrc and inspect fzf's key bindings.

    Returns (ok, message). Used both as the step's state check and by the step itself, so the
    step shows 'done' once fzf is genuinely wired into zsh (and says why when it isn't).
    """
    zsh, fzf = ctx.which("zsh"), ctx.which("fzf")
    if not zsh:
        return False, "zsh is not installed"
    if not fzf:
        return False, "fzf is not installed"
    if "terminal-stuff:fzf" not in ctx.read_text(ZSHRC(ctx)):
        return False, "~/.zshrc has no fzf block (run the 'fzf-zshrc' step)"
    ctx.run([fzf, "--version"], mutating=False)
    res = ctx.run([zsh, "-i", "-c", 'echo "R=$(bindkey \'^R\')"; echo "T=$(bindkey \'^T\')"; echo "C=$(bindkey \'\\ec\')"'],
                  mutating=False, check=False, timeout=timeout,
                  env={"TERM": "xterm-256color", "DISABLE_AUTO_UPDATE": "true"})
    problems = []
    for key, label, widget in (("R", "Ctrl-R", "fzf-history-widget"), ("T", "Ctrl-T", "fzf-file-widget"),
                               ("C", "Alt-C", "fzf-cd-widget")):
        line = next((ln for ln in res.out.splitlines() if ln.startswith(key + "=")), "")
        ok = widget in line
        ctx.log.info("fzf verify %s -> %r (%s)", label, line, "ok" if ok else "MISSING")
        if not ok:
            problems.append(f"{label} is not bound to {widget} (got: {line or 'no output'})")
    if problems:
        return False, ("fzf is installed but not wired into zsh:\n  " + "\n  ".join(problems)
                       + "\n  (see the log for zsh's full output)")
    return True, "Ctrl-T / Ctrl-R / Alt-C are bound to fzf widgets in interactive zsh"


def fzf_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (nothing was actually changed)"
    ok, msg = fzf_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


def fzf_verify_check(ctx: Ctx) -> Tuple[bool, str]:
    ok, msg = fzf_probe(ctx, timeout=20)
    return ok, msg.splitlines()[0]


# ------------------------------------------------------------------ nerd font

NERD_FONT_FAMILY = "JetBrainsMono Nerd Font Mono"      # keep in sync with dotfiles/hyper/hyper.js
HYPER_FONT_STACK = f'"{NERD_FONT_FAMILY}", "Symbols Nerd Font Mono", "DejaVu Sans Mono", Menlo, monospace'
NERD_FONT_URL = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz"
NERD_FONT_FILES = ("JetBrainsMonoNerdFontMono-Regular.ttf", "JetBrainsMonoNerdFontMono-Bold.ttf")


def font_dir(ctx: Ctx) -> Path:
    if ctx.osinfo.os == "macos":
        return ctx.home / "Library" / "Fonts"
    return ctx.home / ".local" / "share" / "fonts" / "JetBrainsMonoNerdFont"


def font_files_present(ctx: Ctx) -> bool:
    return all((font_dir(ctx) / f).is_file() for f in NERD_FONT_FILES)


def font_check(ctx: Ctx) -> Tuple[bool, str]:
    return font_files_present(ctx), str(font_dir(ctx))


def font_install(ctx: Ctx) -> str:
    # Mono = single-width icons (what terminals want); regular = same font, wider icons (some editors).
    pick = lambda n: n.endswith(".ttf") and (n.startswith("JetBrainsMonoNerdFontMono-")     # noqa: E731
                                              or n.startswith("JetBrainsMonoNerdFont-"))
    dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / "JetBrainsMono.tar.xz"
    ctx.download(NERD_FONT_URL, dl)
    if ctx.dry_run and not dl.exists():
        ctx.info(f"[dry-run] would extract fonts into {font_dir(ctx)} and run fc-cache")
        return "would install JetBrainsMono Nerd Font"
    names = ctx.extract_tar(dl, font_dir(ctx), pick)
    if not names:
        raise StepError("archive contained no JetBrainsMono Nerd Font files")
    if ctx.which("fc-cache"):
        ctx.run(["fc-cache", "-f", font_dir(ctx)])
    return f"installed {len(names)} font files into {font_dir(ctx)}"


def font_probe(ctx: Ctx) -> Tuple[bool, str]:
    """Read-only: files exist AND (where fontconfig exists) the family resolves and has Nerd glyphs."""
    if not font_files_present(ctx):
        return False, f"font files missing in {font_dir(ctx)} (run the 'nerdfont-install' step)"
    if not ctx.which("fc-list"):
        return True, f"font files present in {font_dir(ctx)} (no fontconfig here; restart apps to pick it up)"
    # U+E0B0 powerline arrow, U+F09B GitHub icon, U+E718 nodejs: only Nerd-patched fonts have these.
    out = ctx.run(["fc-list", f"{NERD_FONT_FAMILY}:charset=e0b0 f09b e718", "family", "style"],
                  mutating=False).out
    styles = out.lower()
    if NERD_FONT_FAMILY.lower() not in styles:
        return False, (f"fontconfig doesn't list '{NERD_FONT_FAMILY}' with the Nerd glyphs; "
                       "try `fc-cache -f` and re-run, see log")
    missing = [st for st in ("regular", "bold") if st not in styles]
    if missing:
        return False, f"'{NERD_FONT_FAMILY}' is missing style(s): {', '.join(missing)}"
    match = ctx.run(["fc-match", NERD_FONT_FAMILY, "family"], mutating=False).out.strip()
    if NERD_FONT_FAMILY.lower() not in match.lower():
        return False, f"fontconfig resolves '{NERD_FONT_FAMILY}' to '{match}' instead"
    return True, f"'{NERD_FONT_FAMILY}' resolves and contains powerline/devicon glyphs"


def font_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (nothing was actually changed)"
    ok, msg = font_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


# ------------------------------------------------------------------ hyper
#
# Sixel image support (added for the "sixel-capable terminal" leg of the display chain -- see
# dotfiles/tmux/tmux.conf) only ever shipped in Hyper's v4.0.0-canary.4/.5 prereleases (2023-07);
# it never reached a stable release, and the project has had no release of ANY kind since, so
# "latest" (which the GitHub API defines as the newest *non-prerelease*) is permanently stuck on
# v3.4.1 -- nine months *before* that work started. Canary.5 is therefore not "a slightly newer
# build", it's the ONLY build with sixel at all, and there is nothing newer to eventually settle
# on. We track which tag is installed in a sentinel file so `hyper-install` can tell a stale
# pre-canary Hyper apart from an up-to-date one and offer to upgrade.
HYPER_APP_DIR = lambda ctx: ctx.home / "Applications" / "Hyper.app"          # noqa: E731 (macOS)
HYPER_TAG_FILE = lambda ctx: ctx.home / ".cache" / "terminal-stuff" / "hyper-installed-tag.txt"  # noqa: E731


def hyper_path(ctx: Ctx) -> Optional[str]:
    cands = [ctx.which("hyper"), "/Applications/Hyper.app", str(HYPER_APP_DIR(ctx)),
             "/opt/Hyper/hyper", str(HYPER_APPIMAGE(ctx))]
    return next((c for c in cands if c and os.path.exists(c)), None)


def hyper_installed_tag(ctx: Ctx) -> Optional[str]:
    f = HYPER_TAG_FILE(ctx)
    return ctx.read_text(f).strip() or None if f.is_file() else None


def hyper_check(ctx: Ctx) -> Tuple[bool, str]:
    p = hyper_path(ctx)
    if not p:
        return False, "hyper not found"
    tag = hyper_installed_tag(ctx)
    if tag and "canary" in tag:
        return True, f"{p}  ({tag}, sixel-capable)"
    return False, f"{p} is {tag or 'an unknown/pre-canary build'} -- no sixel support; needs the canary build"


def hyper_latest_canary(ctx: Ctx) -> dict:
    releases = ctx.fetch_json("https://api.github.com/repos/vercel/hyper/releases?per_page=30")
    canaries = [r for r in releases if r.get("prerelease")]
    if not canaries:
        raise StepError("no prerelease/canary Hyper release found on GitHub (project may have "
                        "resumed regular releases -- check https://github.com/vercel/hyper/releases)")
    return max(canaries, key=lambda r: r.get("published_at", ""))


def _pick_asset(ctx: Ctx, assets: list, suffix: str, own: Tuple[str, ...], other: Tuple[str, ...]):
    cands = [a for a in assets if a["name"].lower().endswith(suffix)
             and not any(t in a["name"].lower() for t in other)]
    cands.sort(key=lambda a: not any(t in a["name"].lower() for t in own))
    return cands[0] if cands else None


def hyper_install(ctx: Ctx) -> str:
    release = hyper_latest_canary(ctx)
    tag = release.get("tag_name", "")
    assets = [a for a in release.get("assets", []) if a.get("name")]
    ctx.log.info("hyper %s assets: %s", tag, [a["name"] for a in assets])
    own = ("x86_64", "amd64", "x64") if ctx.osinfo.arch == "x86_64" else ("arm64", "aarch64")
    other = ("arm64", "aarch64") if ctx.osinfo.arch == "x86_64" else ("x86_64", "amd64", "x64")

    if ctx.osinfo.os == "macos":
        suffix = "-mac-arm64.zip" if ctx.osinfo.arch != "x86_64" else "-mac-x64.zip"
        asset = next((a for a in assets if a["name"].lower().endswith(suffix.lower())), None)
        if not asset:
            raise StepError(f"no '{suffix}' asset in Hyper release {tag}")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if not ctx.dry_run:
            ctx.extract_archive(dl, HYPER_APP_DIR(ctx).parent / "_hyper_zip_tmp", strip_common_dir=False)
            src = HYPER_APP_DIR(ctx).parent / "_hyper_zip_tmp" / "Hyper.app"
            if not src.is_dir():
                raise StepError(f"expected Hyper.app inside {asset['name']}, didn't find it")
            if HYPER_APP_DIR(ctx).exists():
                ctx.run(["rm", "-rf", HYPER_APP_DIR(ctx)])
            ctx.run(["mv", src, HYPER_APP_DIR(ctx)])
            ctx.run(["rm", "-rf", src.parent])
        kind = "zip"
    else:
        kind = {"apt": "deb", "dnf": "rpm"}.get(ctx.osinfo.pm or "", "AppImage")
        asset = _pick_asset(ctx, assets, "." + kind.lower(), own, other)
        if not asset:
            names = ", ".join(a["name"] for a in assets) or "none"
            raise StepError(f"no .{kind} asset for {ctx.osinfo.arch} in Hyper release {tag} (assets: {names})")
        dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / asset["name"]
        ctx.download(asset["browser_download_url"], dl)
        if kind == "deb":
            ctx.run(["apt-get", "install", "-y", dl], sudo=True, env={"DEBIAN_FRONTEND": "noninteractive"})
        elif kind == "rpm":
            ctx.run(["dnf", "install", "-y", dl], sudo=True)
        else:
            dest = HYPER_APPIMAGE(ctx)
            ctx.mkdir(dest.parent)
            ctx.run(["install", "-m", "755", dl, dest])

    if ctx.dry_run:
        return f"would install Hyper {tag} ({kind})"
    ctx.write_text(HYPER_TAG_FILE(ctx), tag + "\n")
    return f"installed Hyper {tag} ({kind}) -- sixel-capable"


def hyper_config_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.home / ".hyper.js"
    return p.exists(), str(p)


def hyper_config_run(ctx: Ctx) -> str:
    dest = ctx.home / ".hyper.js"
    if dest.exists():
        return "~/.hyper.js already exists; left untouched"
    tpl = ctx.root / "dotfiles" / "hyper" / "hyper.js"
    if not tpl.is_file():
        raise StepError(f"missing template: {tpl}")
    text = tpl.read_text(encoding="utf-8").replace("__ZSH__", ctx.which("zsh") or "").replace("__FONT_FAMILY__", HYPER_FONT_STACK)
    ctx.write_text(dest, text)
    return "created ~/.hyper.js from dotfiles/hyper/hyper.js"


# fontFamily line inside ~/.hyper.js (a JS file, so edit just that one token; never re-generate it)
FONT_LINE_RE = re.compile(r"""^(?P<pre>[ \t]*fontFamily[ \t]*:[ \t]*)(?P<val>'[^'\n]*'|"[^"\n]*"|`[^`\n]*`)""", re.M)


def hyper_font_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.home / ".hyper.js"
    if not p.exists():
        return False, "~/.hyper.js doesn't exist (run the 'hyper-config' step first)"
    m = FONT_LINE_RE.search(ctx.read_text(p))
    if not m:
        return False, "no fontFamily set in ~/.hyper.js"
    first = m.group("val")[1:-1].split(",")[0].strip().strip("\"'")
    return first == NERD_FONT_FAMILY, f"fontFamily starts with '{first}'"


def hyper_font_run(ctx: Ctx) -> str:
    p = ctx.home / ".hyper.js"
    if not p.exists():
        raise StepError("~/.hyper.js doesn't exist; run the 'hyper-config' step first")
    text = ctx.read_text(p)
    value = "'" + HYPER_FONT_STACK + "'"
    m = FONT_LINE_RE.search(text)
    if m:
        new = text[:m.start()] + m.group("pre") + value + text[m.end():]
    else:
        cfg = re.search(r"^([ \t]*)config[ \t]*:[ \t]*\{[ \t]*\n", text, re.M)
        if not cfg:
            raise StepError("couldn't find a `config: {` block in ~/.hyper.js; set this by hand inside it:\n"
                            f"  fontFamily: {value},")
        new = text[:cfg.end()] + f"{cfg.group(1)}  fontFamily: {value},\n" + text[cfg.end():]
    changed = ctx.write_text(p, new)
    note = "" if font_files_present(ctx) else " (font not installed yet: run 'nerdfont-install')"
    return ("set fontFamily in ~/.hyper.js (Hyper reloads its config automatically)" if changed
            else "fontFamily already set") + note


# disableAutoUpdates line inside ~/.hyper.js (same "edit just this one token" approach as fontFamily)
AUTOUPDATE_LINE_RE = re.compile(r"^(?P<pre>[ \t]*disableAutoUpdates[ \t]*:[ \t]*)(?P<val>true|false)", re.M)


def hyper_no_autoupdate_check(ctx: Ctx) -> Tuple[bool, str]:
    p = ctx.home / ".hyper.js"
    if not p.exists():
        return False, "~/.hyper.js doesn't exist (run the 'hyper-config' step first)"
    m = AUTOUPDATE_LINE_RE.search(ctx.read_text(p))
    if not m:
        return False, "no disableAutoUpdates setting in ~/.hyper.js"
    return m.group("val") == "true", f"disableAutoUpdates: {m.group('val')}"


def hyper_no_autoupdate_run(ctx: Ctx) -> str:
    p = ctx.home / ".hyper.js"
    if not p.exists():
        raise StepError("~/.hyper.js doesn't exist; run the 'hyper-config' step first")
    text = ctx.read_text(p)
    m = AUTOUPDATE_LINE_RE.search(text)
    if m:
        new = text[:m.start()] + m.group("pre") + "true" + text[m.end():]
    else:
        cfg = re.search(r"^([ \t]*)config[ \t]*:[ \t]*\{[ \t]*\n", text, re.M)
        if not cfg:
            raise StepError("couldn't find a `config: {` block in ~/.hyper.js; add this by hand inside it:\n"
                            "  disableAutoUpdates: true,")
        new = text[:cfg.end()] + f"{cfg.group(1)}  disableAutoUpdates: true,\n" + text[cfg.end():]
    changed = ctx.write_text(p, new)
    return "set disableAutoUpdates: true in ~/.hyper.js" if changed else "disableAutoUpdates already true"


# ------------------------------------------------------------------ module

def build() -> Module:
    env_c, env_r = zsh_block("zsh-env", "env.zsh")
    omz_c, omz_r = zsh_block("omz", "omz.zsh")
    pure_c, pure_r = zsh_block("pure", "pure.zsh")
    fzf_c, fzf_r = zsh_block("fzf", "fzf.zsh")
    extras_c, extras_r_inner = zsh_block("shell-extras", "shell-extras.zsh")
    omz_ic, omz_ir = clone_step("https://github.com/ohmyzsh/ohmyzsh.git", OMZ_DIR, "oh-my-zsh.sh")
    pure_ic, pure_ir = clone_step("https://github.com/sindresorhus/pure.git", PURE_DIR, "pure.zsh")
    scmb_ic, scmb_ir = clone_step("https://github.com/scmbreeze/scm_breeze.git", SCM_BREEZE_DIR, "scm_breeze.sh")
    scmb_zc, scmb_zr = zsh_block("scm-breeze", "scm_breeze.zsh")

    def extras_r(ctx: Ctx) -> str:
        ctx.mkdir(ctx.home / "apps" / "scripts")
        return extras_r_inner(ctx)

    S = Step
    steps = [
        S("zsh-install", "Install zsh", "Install zsh with the system package manager (brew on Bazzite/macOS).",
          which_check("zsh"), pkg_run("zsh", apt="zsh", dnf="zsh", brew="zsh"), pm_sudo, unix_only),
        S("zsh-env", "zshrc: environment (brew PATH)", "Add a managed block to ~/.zshrc that puts Homebrew and ~/.local/bin on PATH.",
          env_c, env_r, supported=unix_only),
        S("zsh-chsh", "Set zsh as your login shell (chsh)", "Actually changes the account's login shell to zsh "
          "(adds it to /etc/shells first if needed) -- fixes tmux/SSH/other programs that fall back to $SHELL "
          "instead of zsh, on top of the tmux-specific fix in dotfiles/tmux/set-default-shell.sh. Needs sudo. "
          "Opt-in: changes system account state, not just files under $HOME.",
          login_shell_check, login_shell_run, needs_sudo=lambda ctx: True, supported=unix_only, default=False),
        S("shell-extras", "zshrc: shell extras", "Managed ~/.zshrc block: ~/apps/scripts on PATH, python3->python alias, "
          "DOTNET_CLI_TELEMETRY_OPTOUT, and podman<->docker compatibility (alias + DOCKER_HOST).",
          extras_c, extras_r, supported=unix_only),
        S("omz-install", "Install oh-my-zsh", "Clone oh-my-zsh into ~/.oh-my-zsh (does not touch ~/.zshrc or your shell).",
          omz_ic, omz_ir, supported=unix_only),
        S("omz-zshrc", "zshrc: oh-my-zsh", "Managed ~/.zshrc block: load oh-my-zsh with the git plugin and no theme (pure provides the prompt).",
          omz_c, omz_r, supported=unix_only),
        S("pure-install", "Install pure prompt", "Clone sindresorhus/pure into ~/.zsh/pure.",
          pure_ic, pure_ir, supported=unix_only),
        S("pure-zshrc", "zshrc: pure prompt", "Managed ~/.zshrc block: enable the pure prompt (after oh-my-zsh).",
          pure_c, pure_r, supported=unix_only),
        S("scm-breeze-install", "Install scm_breeze", "Clone scmbreeze/scm_breeze into ~/.scm_breeze (git shortcuts/keybindings).",
          scmb_ic, scmb_ir, supported=unix_only),
        S("scm-breeze-config", "scm_breeze: config files", "Create ~/.scmbrc and ~/.git.scmbrc from scm_breeze's example templates (only if missing; never overwrites your edits).",
          scm_breeze_config_check, scm_breeze_config_run, supported=unix_only),
        S("scm-breeze-zshrc", "zshrc: scm_breeze", "Managed ~/.zshrc block: load scm_breeze -- but only outside a Claude Code session "
          "(its git wrapper/keybindings can error when Claude shells out to git; skipped whenever $CLAUDECODE is set).",
          scmb_zc, scmb_zr, supported=unix_only),
        S("fzf-install", "Install fzf", "Install fzf with the system package manager.",
          which_check("fzf"), pkg_run("fzf", apt="fzf", dnf="fzf", brew="fzf"), pm_sudo, unix_only),
        S("fzf-zshrc", "zshrc: fzf integration", "Managed ~/.zshrc block: fzf key bindings (Ctrl-T/Ctrl-R/Alt-C) and completion; handles old and new fzf.",
          fzf_c, fzf_r, supported=unix_only),
        S("fzf-verify", "Verify fzf works in zsh", "Start an interactive zsh with your real ~/.zshrc and confirm Ctrl-T/Ctrl-R/Alt-C are bound to fzf. Read-only.",
          fzf_verify_check, fzf_verify, supported=unix_only),
        S("nerdfont-install", "Install JetBrainsMono Nerd Font", "Download JetBrainsMono Nerd Font (7 MB, GitHub release) into ~/.local/share/fonts (~/Library/Fonts on macOS) and refresh the font cache. No sudo.",
          font_check, font_install, supported=unix_only),
        S("nerdfont-verify", "Verify Nerd Font", "Confirm fontconfig resolves 'JetBrainsMono Nerd Font Mono' (regular + bold) and that it contains Nerd glyphs. Read-only.",
          lambda ctx: font_probe(ctx), font_verify, supported=unix_only),
        S("hyper-install", "Install Hyper terminal (canary, for sixel)", "Installs the latest v4 canary build, the only Hyper build with sixel image support -- it never reached a stable release, and the project has had no release since 2023-07. .deb/.rpm/AppImage on Linux, .app on macOS, all from GitHub (not brew cask, which only tracks stable). Re-run to pick up a newer canary if one appears; flags an old/stable install as needing an upgrade.",
          hyper_check, hyper_install, pm_sudo, unix_only),
        S("hyper-config", "Hyper: config", "Create ~/.hyper.js from dotfiles/hyper/hyper.js with zsh as the shell and the Nerd Font. Never overwrites an existing file (use 'Hyper: use Nerd Font' for those).",
          hyper_config_check, hyper_config_run, supported=unix_only),
        S("hyper-font", "Hyper: use Nerd Font", "Set fontFamily in ~/.hyper.js to JetBrainsMono Nerd Font Mono (with fallbacks). Edits only that one line of an existing config (backed up first).",
          hyper_font_check, hyper_font_run, supported=unix_only),
        S("hyper-no-autoupdate", "Hyper: disable auto-update", "Set disableAutoUpdates: true in ~/.hyper.js, so the canary build can't silently self-update to a newer *stable* release and lose sixel support. Edits only that one line (backed up first).",
          hyper_no_autoupdate_check, hyper_no_autoupdate_run, supported=unix_only),
    ]
    return Module("terminal-env", "Terminal environment (zsh, fzf, Nerd Font, Hyper)",
                  "zsh + oh-my-zsh + pure prompt, fzf with verified zsh integration, a Nerd Font, and the Hyper terminal.",
                  steps)
