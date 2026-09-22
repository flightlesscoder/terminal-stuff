"""Core model: Step/Module, the execution context, and the (dry-run aware) helpers.

Steps must do every mutation through Ctx (run / write_text / ensure_block / mkdir / download /
git_clone / install_pkg) so that --dry-run is trustworthy and everything is logged.
"""
from __future__ import annotations

import difflib
import logging
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import traceback
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .osinfo import OsInfo


class StepError(Exception):
    """A step failed in an expected, explainable way (message is shown to the user)."""


@dataclass
class CmdResult:
    rc: int
    out: str
    skipped: bool = False


# ------------------------------------------------------------------ model

@dataclass
class Step:
    id: str
    title: str
    description: str
    check: Callable[["Ctx"], Tuple[bool, str]]     # -> (already_done, detail); must be read-only
    run: Callable[["Ctx"], Optional[str]]          # mutating; raise StepError on failure
    needs_sudo: Callable[["Ctx"], bool] = lambda ctx: False
    supported: Callable[["Ctx"], Optional[str]] = lambda ctx: None   # -> reason if unsupported
    default: bool = True                            # pre-selected when not already done


@dataclass
class Module:
    id: str
    title: str
    description: str
    steps: List[Step] = field(default_factory=list)


@dataclass
class StepState:
    kind: str        # done | todo | unsupported | unknown
    detail: str = ""


@dataclass
class StepResult:
    module: str
    step: str
    status: str      # ok | failed | skipped
    detail: str = ""
    seconds: float = 0.0


def check_step(ctx: "Ctx", step: Step) -> StepState:
    """Evaluate a step's state without letting a buggy check crash the UI."""
    try:
        why = step.supported(ctx)
        if why:
            state = StepState("unsupported", why)
        else:
            done, detail = step.check(ctx)
            state = StepState("done" if done else "todo", detail)
    except Exception as e:                                # noqa: BLE001
        ctx.log.debug("check %s raised:\n%s", step.id, traceback.format_exc())
        state = StepState("unknown", f"check failed: {e}")
    ctx.log.debug("check %-22s -> %s (%s)", step.id, state.kind, state.detail)
    return state


def run_steps(ctx: "Ctx", selected: Sequence[Tuple[Module, Step]],
              on_event: Callable[..., None] = lambda *a, **k: None) -> List[StepResult]:
    """Run steps in order. A failing step doesn't stop the others (they're isolated)."""
    results: List[StepResult] = []
    ctx.log.info("run: %d step(s), dry_run=%s: %s", len(selected), ctx.dry_run,
                 ", ".join(f"{m.id}/{s.id}" for m, s in selected))
    for mod, step in selected:
        t0 = time.time()
        ctx.log.info("=== STEP %s/%s START: %s", mod.id, step.id, step.title)
        on_event("start", mod, step, None)
        try:
            why = step.supported(ctx)
            if why:
                res = StepResult(mod.id, step.id, "skipped", why)
            else:
                detail = step.run(ctx) or ""
                if ctx.dry_run:
                    detail = f"(dry-run) {detail}"
                res = StepResult(mod.id, step.id, "ok", detail)
        except StepError as e:
            ctx.log.error("step %s failed: %s", step.id, e)
            res = StepResult(mod.id, step.id, "failed", str(e))
        except KeyboardInterrupt:
            ctx.log.error("step %s interrupted by user", step.id)
            res = StepResult(mod.id, step.id, "failed", "interrupted")
            res.seconds = time.time() - t0
            results.append(res)
            on_event("end", mod, step, res)
            raise
        except Exception as e:                            # noqa: BLE001
            ctx.log.error("step %s crashed:\n%s", step.id, traceback.format_exc())
            res = StepResult(mod.id, step.id, "failed", f"unexpected error: {e!r} (see log)")
        res.seconds = time.time() - t0
        ctx.log.info("=== STEP %s/%s END: %s (%.1fs) %s", mod.id, step.id, res.status,
                     res.seconds, res.detail)
        results.append(res)
        on_event("end", mod, step, res)
    return results


# ------------------------------------------------------------------ context

class Ctx:
    def __init__(self, root: Path, osinfo: OsInfo, log: logging.Logger, dry_run: bool = False):
        self.root = root
        self.home = Path(os.path.expanduser("~"))
        self.osinfo = osinfo
        self.log = log
        self.dry_run = dry_run
        self.sink: Callable[[str], None] = lambda line: None   # live output (UI / CLI)
        self._backed_up: set = set()
        self.last_backup: Optional[Path] = None
        self._apt_updated = False
        self._cmd_n = 0

    # -- output -----------------------------------------------------
    def info(self, msg: str) -> None:
        self.log.info(msg)
        self.sink(msg)

    def which(self, name: str) -> Optional[str]:
        return shutil.which(name)

    # -- commands ---------------------------------------------------
    def run(self, argv: Sequence[str], *, sudo: bool = False, check: bool = True,
            mutating: bool = True, cwd: Optional[Path] = None, env: Optional[dict] = None,
            timeout: int = 900) -> CmdResult:
        """Run a command, streaming merged stdout/stderr into the log and the live sink."""
        argv = [str(a) for a in argv]
        used_sudo = sudo and os.geteuid() != 0
        if used_sudo:
            argv = ["sudo", "-n"] + argv          # creds are cached up-front by the runner
        self._cmd_n += 1
        tag = f"cmd#{self._cmd_n}"
        shown = shlex.join(argv)
        if mutating and self.dry_run:
            self.log.info("[%s] DRY-RUN would run: %s", tag, shown)
            self.sink(f"[dry-run] {shown}")
            return CmdResult(0, "", skipped=True)

        full_env = dict(os.environ)
        full_env.update({"GIT_TERMINAL_PROMPT": "0", "HOMEBREW_NO_ENV_HINTS": "1",
                         "HOMEBREW_NO_INSTALL_CLEANUP": "1"})
        if env:
            full_env.update(env)
        self.log.info("[%s] RUN: %s   (cwd=%s%s)", tag, shown, cwd or os.getcwd(),
                      f", extra env: {sorted(env)}" if env else "")
        self.sink(f"$ {shown}")
        t0 = time.time()
        # sudo's cached credential ticket is scoped to the controlling tty/session that authenticated
        # it (cli.py's pre-run `sudo -v`, run attached to the real terminal). start_new_session=True
        # detaches the child into a brand-new session with NO controlling tty at all, so a `sudo -n`
        # in there can't find/match that ticket and fails immediately with "a password is required" --
        # even moments after a real, successful interactive sudo prompt in the same shell. Hit for
        # real: the zsh-chsh step's `sudo -n sh -c ...` failed this way right after typing the
        # password. So: sudo commands stay attached to our own session (ticket matching keeps
        # working); only non-sudo commands get detached (for the killpg-based timeout-kill below).
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors="replace",
                                    cwd=str(cwd) if cwd else None, env=full_env,
                                    start_new_session=not used_sudo)
        except FileNotFoundError:
            self.log.error("[%s] command not found: %s", tag, argv[0])
            raise StepError(f"command not found: {argv[0]}")
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            try:
                if used_sudo:
                    proc.kill()                   # not detached into its own process group; plain kill
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass

        timer = threading.Timer(timeout, _kill)
        timer.start()
        lines: List[str] = []
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                lines.append(line)
                self.log.debug("[%s] | %s", tag, line[:2000])
                self.sink(line)
            rc = proc.wait()
        except BaseException:
            try:
                if used_sudo:
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            self.log.error("[%s] aborted after %.1fs", tag, time.time() - t0)
            raise
        finally:
            timer.cancel()
        self.log.info("[%s] exit=%s in %.1fs%s", tag, rc, time.time() - t0,
                      " (TIMED OUT)" if timed_out.is_set() else "")
        if timed_out.is_set():
            raise StepError(f"timed out after {timeout}s: {shown}")
        if check and rc != 0:
            tail = "\n".join(lines[-8:])
            hint = ""
            if sudo and "password is required" in tail:
                hint = " (sudo credentials expired; re-run and enter your password when asked)"
            raise StepError(f"command failed (exit {rc}): {shown}{hint}\n{tail}")
        return CmdResult(rc, "\n".join(lines))

    def install_pkg(self, *, apt: Optional[str] = None, dnf: Optional[str] = None,
                    brew: Optional[str] = None) -> None:
        pm = self.osinfo.pm
        if pm is None:
            hint = ("install Homebrew (https://brew.sh) — Bazzite is immutable, so use brew/flatpak/distrobox"
                    if self.osinfo.immutable else "no supported package manager found (brew/apt/dnf)")
            raise StepError(hint)
        name = {"apt": apt, "dnf": dnf, "brew": brew}.get(pm)
        if not name:
            raise StepError(f"no package name known for package manager '{pm}'")
        if pm == "apt":
            if not self._apt_updated:
                self.run(["apt-get", "update"], sudo=True)
                self._apt_updated = True
            self.run(["apt-get", "install", "-y", name], sudo=True,
                     env={"DEBIAN_FRONTEND": "noninteractive"})
        elif pm == "dnf":
            self.run(["dnf", "install", "-y", name], sudo=True)
        elif pm == "brew":
            self.run(["brew", "install", name])

    def git_clone(self, url: str, dest: Path, depth: int = 1) -> None:
        if not self.which("git"):
            raise StepError("git is required (see setup/doctor.sh)")
        self.mkdir(dest.parent)
        self.run(["git", "clone", "--depth", str(depth), url, dest])

    # -- files ------------------------------------------------------
    def mkdir(self, path: Path) -> None:
        if path.is_dir():
            return
        if self.dry_run:
            self.log.info("DRY-RUN would mkdir -p %s", path)
            self.sink(f"[dry-run] mkdir -p {path}")
            return
        path.mkdir(parents=True, exist_ok=True)
        self.log.info("mkdir -p %s", path)

    def _backup(self, path: Path) -> Optional[Path]:
        real = Path(os.path.realpath(path))
        if not real.exists() or real in self._backed_up:
            return None
        bak = real.with_name(f"{real.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(real, bak)
        self._backed_up.add(real)
        self.last_backup = bak
        self.log.info("backup %s -> %s", real, bak)
        self.sink(f"backed up {real.name} -> {bak.name}")
        return bak

    def read_text(self, path: Path) -> str:
        try:
            return Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write_text(self, path: Path, text: str, mode: Optional[int] = None) -> bool:
        """Write (backing up + logging a diff). Returns True if content changed."""
        old = self.read_text(path)
        if old == text:
            self.log.info("unchanged: %s", path)
            return False
        diff = "".join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                            f"a/{path}", f"b/{path}"))
        self.log.debug("diff for %s:\n%s", path, diff or "(new/empty file)")
        if self.dry_run:
            self.log.info("DRY-RUN would write %s (%d bytes)", path, len(text))
            if Path(os.path.realpath(path)).exists():
                self.sink(f"[dry-run] back up {path} -> {path.name}.bak-<date>")
            self.sink(f"[dry-run] write {path}")
            return True
        self._backup(path)
        real = Path(os.path.realpath(path))          # write through symlinks
        real.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(real.parent), prefix=f".{real.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            if mode is not None:
                os.chmod(tmp, mode)
            elif real.exists():
                shutil.copymode(real, tmp)
            os.replace(tmp, real)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        self.log.info("wrote %s (%d bytes)", real, len(text))
        self.sink(f"wrote {path}")
        return True

    @staticmethod
    def _markers(name: str, comment: str) -> Tuple[str, str]:
        return (f"{comment} >>> terminal-stuff:{name} >>>", f"{comment} <<< terminal-stuff:{name} <<<")

    def _splice(self, text: str, name: str, body: str, comment: str = "#") -> str:
        begin, end = self._markers(name, comment)
        block = f"{begin}\n{body.rstrip()}\n{end}\n"
        i = text.find(begin)
        if i >= 0:
            j = text.find(end, i)
            if j < 0:
                raise StepError(f"found '{begin}' without matching end marker; fix the file by hand")
            j += len(end)
            if text[j:j + 1] == "\n":
                j += 1
            return text[:i] + block + text[j:]
        if not text:
            return block
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block

    def render_block(self, name: str, body: str, comment: str = "#") -> str:
        """A file consisting solely of one managed block."""
        return self._splice("", name, body, comment)

    def block_current(self, path: Path, name: str, body: str, comment: str = "#") -> bool:
        text = self.read_text(path)
        try:
            return self._splice(text, name, body, comment) == text
        except StepError:
            return False

    def ensure_block(self, path: Path, name: str, body: str, comment: str = "#") -> bool:
        """Insert/replace a marked block in a config file, leaving everything else untouched."""
        text = self.read_text(path)
        return self.write_text(path, self._splice(text, name, body, comment))

    def extract_tar(self, archive: Path, dest: Path, pick) -> List[str]:
        """Extract members whose base name satisfies pick(name) flat into dest. Returns names."""
        import tarfile
        try:
            with tarfile.open(archive) as tf:
                names = [m.name for m in tf.getmembers() if m.isfile() and pick(os.path.basename(m.name))]
                if self.dry_run:
                    self.log.info("DRY-RUN would extract %d file(s) from %s to %s", len(names), archive, dest)
                    self.sink(f"[dry-run] extract {len(names)} file(s) to {dest}")
                    return names
                dest.mkdir(parents=True, exist_ok=True)
                for m in tf.getmembers():
                    if m.isfile() and pick(os.path.basename(m.name)):
                        m.name = os.path.basename(m.name)          # flatten; also blocks path traversal
                        tf.extract(m, dest)
        except (tarfile.TarError, OSError) as e:
            raise StepError(f"could not extract {archive}: {e}")
        self.log.info("extracted %d file(s) to %s: %s", len(names), dest, ", ".join(sorted(names)))
        return names

    def extract_archive(self, archive: Path, dest: Path, strip_common_dir: bool = True) -> int:
        """Extract a whole .tar.gz/.tar/.zip tree into dest, replacing it if it already exists.

        strip_common_dir drops a single shared top-level directory (e.g. GitHub release tarballs
        wrapped in "toolname-linux-x64/"), so dest ends up holding the tool's own layout directly.
        Returns the number of files written. Rejects absolute paths and '..' components.
        """
        import shutil as _shutil
        import tarfile
        import zipfile

        def names_and_open(extract_to: Path):
            if zipfile.is_zipfile(archive):
                zf = zipfile.ZipFile(archive)
                return zf, [i.filename for i in zf.infolist() if not i.is_dir()], \
                    (lambda n, dst: zf.extract(n, dst))
            tf = tarfile.open(archive)
            return tf, [m.name for m in tf.getmembers() if m.isfile()], \
                (lambda n, dst: tf.extract(tf.getmember(n), dst, filter="data"))

        try:
            handle, members, extract_one = names_and_open(dest)
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
            raise StepError(f"could not open {archive}: {e}")
        with handle:
            for n in members:
                if os.path.isabs(n) or ".." in Path(n).parts:
                    raise StepError(f"refusing to extract unsafe path '{n}' from {archive}")
            strip = ""
            if strip_common_dir and members and all("/" in n for n in members):
                tops = {n.split("/", 1)[0] for n in members}
                if len(tops) == 1:
                    strip = tops.pop() + "/"
            if self.dry_run:
                self.log.info("DRY-RUN would extract %d file(s) from %s to %s (strip=%r)",
                             len(members), archive, dest, strip)
                self.sink(f"[dry-run] extract {len(members)} file(s) to {dest}")
                return len(members)
            if dest.exists():
                _shutil.rmtree(dest)
            tmp = dest.with_name(dest.name + ".part")
            if tmp.exists():
                _shutil.rmtree(tmp)
            tmp.mkdir(parents=True)
            try:
                for n in members:
                    extract_one(n, tmp)
                if strip:                                    # move the inner dir's contents up one level
                    inner = tmp / strip.rstrip("/")
                    for child in inner.iterdir():
                        _shutil.move(str(child), tmp / child.name)
                    inner.rmdir()
                tmp.rename(dest)
            except BaseException:
                _shutil.rmtree(tmp, ignore_errors=True)
                raise
        self.log.info("extracted %d file(s) from %s to %s (stripped %r)", len(members), archive, dest, strip)
        return len(members)

    def symlink(self, target: Path, link: Path) -> bool:
        """Make link -> target, replacing whatever is at link. Returns True if it changed anything."""
        if self.dry_run:
            self.log.info("DRY-RUN would symlink %s -> %s", link, target)
            self.sink(f"[dry-run] link {link} -> {target}")
            return True
        current = os.path.realpath(link) if os.path.islink(link) or link.exists() else None
        if current == os.path.realpath(target):
            return False
        self.mkdir(link.parent)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
        self.log.info("symlink %s -> %s", link, target)
        self.sink(f"linked {link.name} -> {target}")
        # PATH is only scanned for existing dirs once at startup (osinfo.augment_path); a bin dir a step
        # just created (e.g. ~/.local/bin on a fresh machine) wouldn't be on it yet for the rest of this
        # run, so a which() done right after installing something here would wrongly say "not found".
        parent = str(link.parent)
        parts = os.environ.get("PATH", "").split(os.pathsep)
        if parent not in parts:
            os.environ["PATH"] = os.pathsep.join([parent] + parts)
        return True

    # -- network ----------------------------------------------------
    def fetch_json(self, url: str):
        import json
        self.log.info("GET %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "terminal-stuff-setup",
                                                   "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:                            # noqa: BLE001
            raise StepError(f"could not fetch {url}: {e}")

    def download(self, url: str, dest: Path) -> None:
        if self.dry_run:
            self.log.info("DRY-RUN would download %s -> %s", url, dest)
            self.sink(f"[dry-run] download {url}")
            return
        self.mkdir(dest.parent)
        self.log.info("download %s -> %s", url, dest)
        self.sink(f"downloading {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "terminal-stuff-setup"})
        tmp = dest.with_name(dest.name + ".part")
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                done, next_mark = 0, 10
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total and done * 100 // total >= next_mark:
                        self.log.debug("download progress %d%% (%d/%d)", done * 100 // total, done, total)
                        next_mark += 10
            os.replace(tmp, dest)
        except Exception as e:                            # noqa: BLE001
            if tmp.exists():
                tmp.unlink()
            raise StepError(f"download failed: {url}: {e}")
        self.log.info("downloaded %s (%d bytes)", dest, dest.stat().st_size)
