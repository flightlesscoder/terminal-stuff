"""Verbose per-run logging into <repo>/logs with a hard cap on total disk usage."""
from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import List, Tuple

MAX_TOTAL_BYTES = 25 * 1024 * 1024   # whole logs/ folder
MAX_FILES = 50                       # oldest runs are dropped beyond this
PER_RUN_BYTES = 5 * 1024 * 1024      # one run rotates at this size...
PER_RUN_BACKUPS = 2                  # ...keeping this many older chunks (so <= 15 MB/run)

PATTERN = "setup-*.log*"


def prune(log_dir: Path, keep_prefix: str = "") -> List[Path]:
    """Delete the oldest logs until under the file-count and total-size caps."""
    files = [p for p in log_dir.glob(PATTERN) if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime)          # oldest first
    total = sum(p.stat().st_size for p in files)
    removed: List[Path] = []
    for p in list(files):
        if len(files) - len(removed) <= MAX_FILES and total <= MAX_TOTAL_BYTES:
            break
        if keep_prefix and p.name.startswith(keep_prefix):
            continue                                       # never delete the current run
        try:
            size = p.stat().st_size
            p.unlink()
            total -= size
            removed.append(p)
        except OSError:
            pass
    return removed


def init(root: Path, console: bool = False) -> Tuple[logging.Logger, Path]:
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = log_dir / f"setup-{stamp}-{os.getpid()}.log"

    log = logging.getLogger("setup")
    log.setLevel(logging.DEBUG)
    log.handlers[:] = []
    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=PER_RUN_BYTES, backupCount=PER_RUN_BACKUPS, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-5s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        log.addHandler(ch)

    latest = log_dir / "latest.log"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(path.name)
    except OSError:
        pass

    removed = prune(log_dir, keep_prefix=path.stem)
    if removed:
        log.debug("pruned %d old log file(s): %s", len(removed), ", ".join(p.name for p in removed))
    return log, path
