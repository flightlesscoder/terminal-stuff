"""Module: obsidian -- a git-tracked vault at ~/apps/gitvault, with settings/theme/plugins/font
pre-configured to match a known-good setup.

Obsidian's settings files (.obsidian/*.json) aren't documented anywhere official -- it's a
closed-source Electron app -- so every key name here (APP_JSON/APPEARANCE_JSON/CORE_PLUGINS_JSON)
was verified against several real, public vaults on GitHub rather than guessed. Plugin ids/repos
came from obsidianmd/obsidian-releases' community-plugins.json (the canonical registry Obsidian
itself reads from), and each pinned version was confirmed to exist as a real release with
manifest.json/main.js (styles.css where the plugin ships one) as release assets, the same three
files Obsidian's own in-app installer downloads.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from ..core import Ctx, Module, Step, StepError
from ._common import unix_only

VAULT_DIR = lambda ctx: ctx.home / "apps" / "gitvault"      # noqa: E731
GIT_NAME = "flightless coder"
GIT_EMAIL = "flightless coder"

GITIGNORE = """workspace.json
cursor-positions.json
.obsidian/plugins/remember-cursor-position/cursor-positions.json
.obsidian/workspace.json
"""
GITATTRIBUTES = "*.md text=auto\n"

ACCENT_HEX = "#f25cf5"          # R242 G92 B245 -- also recorded in themes/palette.json
THEME_NAME = "Royal Velvet"
THEME_REPO = "caro401/royal-velvet"                          # default branch: main
TEXT_FONT_FAMILY = "UbuntuMono Nerd Font Mono"
NERD_FONT_URL = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/UbuntuMono.tar.xz"
NERD_FONT_FILES = ("UbuntuMonoNerdFontMono-Regular.ttf", "UbuntuMonoNerdFontMono-Bold.ttf")

APP_JSON = {
    "alwaysUpdateLinks": True,
    "newLinkFormat": "shortest",
    "attachmentFolderPath": "GeneralAttachments",
    "newFileLocation": "current",
    "defaultViewMode": "source",           # "source" = Editing view (vs. "preview" = Reading view)
    "livePreview": True,
    "promptDelete": True,
    "useTab": True,
    "tabSize": 4,                          # "indent visual width"
    "vimMode": True,
    "spellcheck": True,
    "showLineNumber": True,
    "foldHeading": True,
    "foldIndent": True,
    "showIndentGuide": True,
    "readableLineLength": True,
    "autoPairBrackets": True,
    "autoPairMarkdown": True,
    "smartIndentList": True,               # "smart lists"
    "focusNewTab": True,
    "showInlineTitle": True,
    "autoConvertHtml": True,               # "convert pasted HTML to markdown"
}

APPEARANCE_JSON = {
    "theme": "obsidian",                   # dark base color scheme ("moonstone" = light)
    "cssTheme": THEME_NAME,
    "accentColor": ACCENT_HEX,
    "textFontFamily": TEXT_FONT_FAMILY,
    "baseFontSize": 16,
    "showViewHeader": True,                # "show tab title bar"
    "showRibbon": True,
}

# "editor-status" isn't in the user's explicit core-plugin list, but it's the actual plugin behind
# "show editing mode in status bar" they asked for under Editor settings -- enabled for that reason.
CORE_PLUGINS_JSON = {
    "file-explorer": True, "global-search": True, "switcher": True, "graph": True,
    "backlink": True, "outgoing-link": True, "tag-pane": True, "page-preview": True,
    "daily-notes": True, "templates": True, "note-composer": True, "command-palette": True,
    "outline": True, "word-count": True, "file-recovery": True, "canvas": True,
    "bookmarks": True, "bases": True, "editor-status": True,
    "slash-command": False, "markdown-importer": False, "zk-prefixer": False,
    "random-note": False, "slides": False, "audio-recorder": False, "workspaces": False,
    "publish": False, "sync": False, "properties": False, "webviewer": False, "footnotes": False,
}

# id -> (owner/repo, pinned version). ids/repos from obsidianmd/obsidian-releases'
# community-plugins.json; versions are release tags confirmed to exist on each repo (bare version
# string, no "v" prefix -- verified for all 14, not assumed).
PLUGINS = {
    "calendar": ("liamcain/obsidian-calendar-plugin", "1.5.10"),
    "code-styler": ("mayurankv/Obsidian-Code-Styler", "1.1.7"),
    "obsidian-custom-frames": ("ellpeck/ObsidianCustomFrames", "2.4.7"),
    "dataview": ("blacksmithgu/obsidian-dataview", "0.5.67"),
    "obsidian-doubleshift": ("qwyntex/doubleshift", "2.2.1"),
    "execute-code": ("twibiral/obsidian-execute-code", "1.12.0"),
    "obsidian-git": ("vinzent03/obsidian-git", "2.31.1"),
    "homepage": ("mirnovov/obsidian-homepage", "4.0.7"),
    "obsidian-html-plugin": ("nuthrash/obsidian-html-plugin", "1.0.12"),
    "obsidian-image-toolkit": ("obsidian-community/obsidian-image-toolkit", "1.4.3"),
    "obsidian-kanban": ("obsidian-community/obsidian-kanban", "2.0.51"),
    "omnisearch": ("scambier/obsidian-omnisearch", "1.24.1"),
    "remember-cursor-position": ("dy-sh/obsidian-remember-cursor-position", "1.0.9"),
    "terminal": ("polyipseity/obsidian-terminal", "3.15.1"),
}


def obsidian_dir(ctx: Ctx) -> Path:
    return VAULT_DIR(ctx) / ".obsidian"


def _has_ref(ctx: Ctx, d: Path, ref: str) -> bool:
    return ctx.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{ref}"],
                   mutating=False, check=False, cwd=d).rc == 0


def _current_branch(ctx: Ctx, d: Path) -> str:
    return ctx.run(["git", "branch", "--show-current"], mutating=False, check=False, cwd=d).out.strip()


# ------------------------------------------------------------------ git init + branches

def git_check(ctx: Ctx) -> Tuple[bool, str]:
    d = VAULT_DIR(ctx)
    if not (d / ".git").is_dir():
        return False, f"{d} is not a git repo yet"
    have_main, have_working = _has_ref(ctx, d, "main"), _has_ref(ctx, d, "working")
    gi_ok, ga_ok = (d / ".gitignore").is_file(), (d / ".gitattributes").is_file()
    if have_main and have_working and gi_ok and ga_ok:
        return True, f"{d} (main + working branches, gitignore/gitattributes committed)"
    missing = [n for n, ok in (("main branch", have_main), ("working branch", have_working),
                               (".gitignore", gi_ok), (".gitattributes", ga_ok)) if not ok]
    return False, f"{d}: missing {', '.join(missing)}"


def git_run(ctx: Ctx) -> str:
    d = VAULT_DIR(ctx)
    ctx.mkdir(d)
    notes = []
    fresh = not (d / ".git").is_dir()
    if fresh:
        if ctx.dry_run:
            notes.append("would git init -b main")
        else:
            ctx.run(["git", "init", "-b", "main"], cwd=d)
            notes.append("git init (main)")
    if ctx.dry_run:
        return "would set up git identity, .gitignore/.gitattributes, main + working branches"

    ctx.run(["git", "config", "user.name", GIT_NAME], cwd=d)
    ctx.run(["git", "config", "user.email", GIT_EMAIL], cwd=d)

    gi, ga = d / ".gitignore", d / ".gitattributes"
    # Only touch main at all if these still need creating -- once committed, they're already
    # present on 'working' too (branched off main after that commit), so a re-run that's already
    # fully set up shouldn't bounce through main and back just to check.
    if not gi.is_file() or not ga.is_file():
        if _current_branch(ctx, d) != "main":
            if _has_ref(ctx, d, "main"):
                ctx.run(["git", "checkout", "main"], cwd=d)
            else:
                raise StepError(f"{d} is an existing git repo without a 'main' branch "
                                f"(currently on '{_current_branch(ctx, d)}'); fix by hand")
        if not gi.is_file():
            ctx.write_text(gi, GITIGNORE)
        if not ga.is_file():
            ctx.write_text(ga, GITATTRIBUTES)
        ctx.run(["git", "add", ".gitignore", ".gitattributes"], cwd=d)
        staged = ctx.run(["git", "diff", "--cached", "--name-only"], mutating=False, check=False, cwd=d).out.strip()
        if staged:
            ctx.run(["git", "commit", "-m", "Add .gitignore and .gitattributes"], cwd=d)
            notes.append("committed .gitignore/.gitattributes on main")

    if not _has_ref(ctx, d, "working"):
        ctx.run(["git", "checkout", "-b", "working"], cwd=d)
        notes.append("created 'working' branch off main")
    elif _current_branch(ctx, d) != "working":
        ctx.run(["git", "checkout", "working"], cwd=d)
        notes.append("checked out 'working'")
    return "; ".join(notes) if notes else "already set up"


# ------------------------------------------------------------------ vault settings (.obsidian/*.json)

def _write_json_if_missing(ctx: Ctx, path: Path, data) -> bool:
    if path.is_file():
        return False
    ctx.write_text(path, json.dumps(data, indent=2) + "\n")
    return True


SETTINGS_FILES = ("app.json", "appearance.json", "core-plugins.json", "community-plugins.json")


def settings_check(ctx: Ctx) -> Tuple[bool, str]:
    od = obsidian_dir(ctx)
    missing = [f for f in SETTINGS_FILES if not (od / f).is_file()]
    return not missing, (", ".join(SETTINGS_FILES) if not missing else f"missing: {', '.join(missing)}")


def settings_run(ctx: Ctx) -> str:
    d = VAULT_DIR(ctx)
    if not ctx.dry_run:
        if not (d / ".git").is_dir():
            raise StepError("vault isn't set up yet; run the 'vault-git-init' step first")
        current = _current_branch(ctx, d)
        if current != "working":
            raise StepError(f"vault repo is on '{current}', not 'working' -- switch to 'working' "
                            "first (that's where vault files, incl. .obsidian settings, get edited)")
    od = obsidian_dir(ctx)
    ctx.mkdir(od)
    ctx.mkdir(d / "GeneralAttachments")             # default location for new attachments
    written = []
    for name, data in (("app.json", APP_JSON), ("appearance.json", APPEARANCE_JSON),
                       ("core-plugins.json", CORE_PLUGINS_JSON),
                       ("community-plugins.json", sorted(PLUGINS))):
        if ctx.dry_run:
            written.append(name)
            continue
        if _write_json_if_missing(ctx, od / name, data):
            written.append(name)
    if ctx.dry_run:
        return f"would write {', '.join(written)}"
    return f"wrote {', '.join(written)}" if written else "all settings files already present"


# ------------------------------------------------------------------ theme (Royal Velvet)

def theme_dir(ctx: Ctx) -> Path:
    return obsidian_dir(ctx) / "themes" / THEME_NAME


def theme_check(ctx: Ctx) -> Tuple[bool, str]:
    d = theme_dir(ctx)
    ok = (d / "manifest.json").is_file() and (d / "theme.css").is_file()
    return ok, str(d)


def theme_run(ctx: Ctx) -> str:
    d = theme_dir(ctx)
    ctx.mkdir(d)
    for fname in ("manifest.json", "theme.css"):
        ctx.download(f"https://raw.githubusercontent.com/{THEME_REPO}/main/{fname}", d / fname)
    if ctx.dry_run:
        return f"would install {THEME_NAME} theme"
    if not (d / "manifest.json").is_file() or not (d / "theme.css").is_file():
        raise StepError(f"download ran but {d} is incomplete")
    return f"installed {THEME_NAME} theme into {d}"


# ------------------------------------------------------------------ community plugins (pinned versions)

def plugin_dir(ctx: Ctx, plugin_id: str) -> Path:
    return obsidian_dir(ctx) / "plugins" / plugin_id


def _installed_version(ctx: Ctx, plugin_id: str) -> str:
    mf = plugin_dir(ctx, plugin_id) / "manifest.json"
    if not mf.is_file():
        return ""
    try:
        return json.loads(ctx.read_text(mf)).get("version", "")
    except (json.JSONDecodeError, OSError):
        return ""


def plugins_check(ctx: Ctx) -> Tuple[bool, str]:
    wrong = [f"{pid} ({_installed_version(ctx, pid) or 'missing'}, want {ver})"
             for pid, (_repo, ver) in PLUGINS.items() if _installed_version(ctx, pid) != ver]
    if not wrong:
        return True, f"{len(PLUGINS)} plugins at pinned versions"
    return False, f"{len(wrong)}/{len(PLUGINS)} need (re)install: {', '.join(wrong)}"


def plugins_run(ctx: Ctx) -> str:
    installed, skipped = [], []
    for pid, (repo, ver) in sorted(PLUGINS.items()):
        if not ctx.dry_run and _installed_version(ctx, pid) == ver:
            skipped.append(pid)
            continue
        d = plugin_dir(ctx, pid)
        ctx.mkdir(d)
        base = f"https://github.com/{repo}/releases/download/{ver}"
        ctx.download(f"{base}/manifest.json", d / "manifest.json")
        ctx.download(f"{base}/main.js", d / "main.js")
        try:
            ctx.download(f"{base}/styles.css", d / "styles.css")    # not every plugin ships one
        except StepError:
            pass
        if ctx.dry_run:
            installed.append(pid)
            continue
        if _installed_version(ctx, pid) != ver:
            raise StepError(f"{pid}: downloaded but manifest.json still doesn't report {ver}")
        installed.append(pid)
    bits = []
    if installed:
        bits.append(f"installed/updated: {', '.join(installed)}")
    if skipped:
        bits.append(f"already at pinned version: {', '.join(skipped)}")
    return "; ".join(bits) if bits else "nothing to do"


# ------------------------------------------------------------------ UbuntuMono Nerd Font

def ubuntu_font_dir(ctx: Ctx) -> Path:
    if ctx.osinfo.os == "macos":
        return ctx.home / "Library" / "Fonts"
    return ctx.home / ".local" / "share" / "fonts" / "UbuntuMonoNerdFont"


def ubuntu_font_files_present(ctx: Ctx) -> bool:
    return all((ubuntu_font_dir(ctx) / f).is_file() for f in NERD_FONT_FILES)


def ubuntu_font_check(ctx: Ctx) -> Tuple[bool, str]:
    return ubuntu_font_files_present(ctx), str(ubuntu_font_dir(ctx))


def ubuntu_font_run(ctx: Ctx) -> str:
    pick = lambda n: n.endswith(".ttf") and (n.startswith("UbuntuMonoNerdFontMono-")           # noqa: E731
                                              or n.startswith("UbuntuMonoNerdFont-"))
    dl = ctx.home / ".cache" / "terminal-stuff" / "downloads" / "UbuntuMono.tar.xz"
    ctx.download(NERD_FONT_URL, dl)
    if ctx.dry_run and not dl.exists():
        ctx.info(f"[dry-run] would extract fonts into {ubuntu_font_dir(ctx)} and run fc-cache")
        return "would install UbuntuMono Nerd Font"
    names = ctx.extract_tar(dl, ubuntu_font_dir(ctx), pick)
    if not names:
        raise StepError("archive contained no UbuntuMono Nerd Font files")
    if ctx.which("fc-cache"):
        ctx.run(["fc-cache", "-f", ubuntu_font_dir(ctx)])
    return f"installed {len(names)} font files into {ubuntu_font_dir(ctx)}"


# ------------------------------------------------------------------ verification

def vault_probe(ctx: Ctx) -> Tuple[bool, str]:
    checks = [
        ("git (main+working, gitignore/gitattributes)", git_check(ctx)[0]),
        ("vault settings (app/appearance/core/community json)", settings_check(ctx)[0]),
        (f"theme ({THEME_NAME})", theme_check(ctx)[0]),
        ("community plugins (pinned versions)", plugins_check(ctx)[0]),
        ("UbuntuMono Nerd Font", ubuntu_font_check(ctx)[0]),
    ]
    bad = [label for label, ok in checks if not ok]
    if bad:
        return False, "not fully set up: " + ", ".join(bad)
    return True, f"vault ready: {VAULT_DIR(ctx)}"


def vault_verify(ctx: Ctx) -> str:
    if ctx.dry_run:
        return "skipped in dry-run (read-only check anyway)"
    ok, msg = vault_probe(ctx)
    if not ok:
        raise StepError(msg)
    return msg


# ------------------------------------------------------------------ module

def build() -> Module:
    S = Step
    return Module("obsidian", "Obsidian vault (~/apps/gitvault)",
                  "A git-tracked Obsidian vault: main+working branches, curated app/appearance settings, "
                  f"the {THEME_NAME} theme, {len(PLUGINS)} pinned community plugins, and the UbuntuMono Nerd Font.", [
        S("vault-git-init", "Vault: git init + branches", f"Create ~/apps/gitvault, git init (local identity "
          f"'{GIT_NAME}'/'{GIT_EMAIL}', not global), .gitignore + .gitattributes (*.md text=auto) committed on "
          "main, then branch to 'working' (where vault files get edited).",
          git_check, git_run, supported=unix_only),
        S("vault-settings", "Vault: settings (app/appearance/core-plugins/community-plugins)",
          "Write .obsidian/app.json, appearance.json, core-plugins.json, community-plugins.json. Needs the "
          "'working' branch checked out (run 'vault-git-init' first). Never overwrites a file that already exists.",
          settings_check, settings_run, supported=unix_only),
        S("vault-theme-install", f"Vault: install {THEME_NAME} theme", f"Download the {THEME_NAME} theme "
          f"({THEME_REPO}) into .obsidian/themes/{THEME_NAME}/.", theme_check, theme_run, supported=unix_only),
        S("vault-plugins-install", "Vault: install community plugins (pinned versions)",
          f"Download manifest.json/main.js/styles.css for {len(PLUGINS)} pinned community plugins into "
          ".obsidian/plugins/<id>/, straight from each plugin's own GitHub release (matches how Obsidian's own "
          "in-app installer fetches a plugin -- no npm/build step). Re-installs only if the pinned version changes.",
          plugins_check, plugins_run, supported=unix_only),
        S("vault-font-install", "Install UbuntuMono Nerd Font", "Download UbuntuMono Nerd Font (7 MB, GitHub "
          "release) into ~/.local/share/fonts (~/Library/Fonts on macOS) and refresh the font cache. No sudo.",
          ubuntu_font_check, ubuntu_font_run, supported=unix_only),
        S("vault-verify", "Verify vault setup", "Read-only: git branches/gitignore/gitattributes, settings "
          "files, theme, plugin versions, and the font are all in place.",
          lambda ctx: vault_probe(ctx), vault_verify, supported=unix_only),
    ])
