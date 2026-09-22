"""curses front-end: pick steps per module, run them with live output, show a summary."""
from __future__ import annotations

import curses
import os
import subprocess
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .cli import compute_states, default_selection, summarize_lines
from .core import Ctx, Module, Step, StepResult, StepState, run_steps

KEY_ESC = 27
MIN_W, MIN_H = 60, 14


class App:
    def __init__(self, ctx: Ctx, modules: List[Module]):
        self.ctx = ctx
        self.log = ctx.log
        self.modules = modules
        self.rows: List[Tuple[str, Module, Optional[Step]]] = []
        for m in modules:
            self.rows.append(("module", m, None))
            self.rows += [("step", m, s) for s in m.steps]
        self.cursor = 1
        self.top = 0
        self.msg = ""
        self.states: Dict[Tuple[str, str], StepState] = {}
        self.selected: set = set()
        self.tail: Deque[str] = deque(maxlen=400)
        self.progress: Dict[Tuple[str, str], str] = {}
        self._last_draw = 0.0
        self.scr = None
        self.refresh_states(reset_selection=True)

    # ---------------------------------------------------------------- state
    def refresh_states(self, reset_selection: bool = False) -> None:
        self.states = compute_states(self.ctx, self.modules)
        if reset_selection:
            self.selected = {(m.id, s.id) for m in self.modules for s in default_selection(self.states, m)}
        else:
            self.selected = {k for k in self.selected if self.states[k].kind != "unsupported"}

    def selectable(self, m: Module, s: Step) -> bool:
        return self.states[(m.id, s.id)].kind != "unsupported"

    def chosen(self) -> List[Tuple[Module, Step]]:
        return [(m, s) for m in self.modules for s in m.steps if (m.id, s.id) in self.selected]

    # ---------------------------------------------------------------- drawing helpers
    def put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.scr.addnstr(y, x, text, max(0, w - x - (1 if y == h - 1 else 0)), attr)
            except curses.error:
                pass

    def init_colors(self) -> None:
        curses.curs_set(0)
        try:
            curses.start_color()
            curses.use_default_colors()
            for i, c in enumerate((curses.COLOR_GREEN, curses.COLOR_RED, curses.COLOR_YELLOW, curses.COLOR_CYAN), 1):
                curses.init_pair(i, c, -1)
        except curses.error:
            pass
        self.C_OK = curses.color_pair(1)
        self.C_BAD = curses.color_pair(2)
        self.C_WARN = curses.color_pair(3)
        self.C_HEAD = curses.color_pair(4) | curses.A_BOLD

    def too_small(self) -> bool:
        h, w = self.scr.getmaxyx()
        if h < MIN_H or w < MIN_W:
            self.scr.erase()
            self.put(0, 0, f"terminal too small ({w}x{h}); need {MIN_W}x{MIN_H}")
            self.scr.refresh()
            return True
        return False

    # ---------------------------------------------------------------- selection screen
    def draw_select(self) -> None:
        self.scr.erase()
        if self.too_small():
            return
        h, w = self.scr.getmaxyx()
        title = " terminal-stuff setup"
        mode = "DRY-RUN" if self.ctx.dry_run else "live"
        self.put(0, 0, title, self.C_HEAD)
        self.put(0, max(len(title) + 2, w - len(mode) - 3), f" {mode} ", self.C_WARN | curses.A_BOLD if self.ctx.dry_run else self.C_OK)
        self.put(1, 1, self.ctx.osinfo.describe(), curses.A_DIM)

        list_top, list_h = 3, h - 3 - 5
        if self.cursor < self.top:
            self.top = self.cursor
        if self.cursor >= self.top + list_h:
            self.top = self.cursor - list_h + 1
        for i in range(list_h):
            idx = self.top + i
            if idx >= len(self.rows):
                break
            kind, m, s = self.rows[idx]
            y = list_top + i
            cur = curses.A_REVERSE if idx == self.cursor else 0
            if kind == "module":
                n_sel = sum((m.id, st.id) in self.selected for st in m.steps)
                n_all = sum(self.selectable(m, st) for st in m.steps)
                box = "[x]" if n_sel and n_sel == n_all else "[~]" if n_sel else "[ ]"
                self.put(y, 1, f"{box} {m.title}", self.C_HEAD | cur)
                self.put(y, max(w - 16, 40), f"{n_sel}/{n_all} selected", curses.A_DIM)
            else:
                st = self.states[(m.id, s.id)]
                key = (m.id, s.id)
                if st.kind == "unsupported":
                    self.put(y, 5, f"[-] {s.title}", curses.A_DIM | cur)
                    self.put(y, 40, "n/a", curses.A_DIM)
                    continue
                box = "[x]" if key in self.selected else "[ ]"
                self.put(y, 5, f"{box} {s.title}", cur)
                label, attr = {"done": ("done ✔", self.C_OK), "todo": ("todo", self.C_WARN),
                               "unknown": ("unknown ?", self.C_BAD)}[st.kind]
                self.put(y, max(w - 14, 46), label, attr)
        if len(self.rows) > list_h:
            self.put(list_top - 1, w - 12, f"({self.cursor + 1}/{len(self.rows)})", curses.A_DIM)

        # description of the highlighted row
        kind, m, s = self.rows[self.cursor]
        y = h - 5
        self.put(y, 0, "─" * (w - 1), curses.A_DIM)
        if kind == "module":
            self.put(y + 1, 1, m.description)
        else:
            st = self.states[(m.id, s.id)]
            self.put(y + 1, 1, s.description)
            self.put(y + 2, 1, f"id: {s.id}   state: {st.kind}" + (f"   {st.detail}" if st.detail else ""), curses.A_DIM)
        if self.msg:
            self.put(y + 3, 1, self.msg, self.C_WARN)
        self.put(h - 1, 0, " ↑↓ move  space toggle  a all  n none  t todo-only  d dry-run  r/enter run  q quit",
                 curses.A_REVERSE)
        self.scr.refresh()

    def toggle(self) -> None:
        kind, m, s = self.rows[self.cursor]
        if kind == "step":
            if not self.selectable(m, s):
                return
            k = (m.id, s.id)
            self.selected.symmetric_difference_update({k})
            self.log.debug("ui: toggle %s -> %s", k, k in self.selected)
        else:
            keys = {(m.id, st.id) for st in m.steps if self.selectable(m, st)}
            if keys <= self.selected:
                self.selected -= keys
            else:
                self.selected |= keys
            self.log.debug("ui: toggle module %s -> %d selected", m.id, len(self.selected))

    def select_loop(self) -> None:
        while True:
            self.draw_select()
            k = self.scr.getch()
            self.msg = ""
            if k in (ord("q"), KEY_ESC):
                self.log.info("ui: quit")
                return
            elif k in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(len(self.rows) - 1, self.cursor + 1)
            elif k == curses.KEY_PPAGE:
                self.cursor = max(0, self.cursor - 8)
            elif k == curses.KEY_NPAGE:
                self.cursor = min(len(self.rows) - 1, self.cursor + 8)
            elif k == curses.KEY_HOME:
                self.cursor = 0
            elif k == curses.KEY_END:
                self.cursor = len(self.rows) - 1
            elif k == ord(" "):
                self.toggle()
            elif k == ord("a"):
                self.selected = {(m.id, s.id) for m in self.modules for s in m.steps if self.selectable(m, s)}
            elif k == ord("n"):
                self.selected = set()
            elif k == ord("t"):
                self.refresh_states(reset_selection=True)
            elif k == ord("d"):
                self.ctx.dry_run = not self.ctx.dry_run
                self.log.info("ui: dry_run=%s", self.ctx.dry_run)
            elif k in (ord("r"), curses.KEY_ENTER, 10, 13):
                self.execute()
            # KEY_RESIZE just falls through to a redraw

    # ---------------------------------------------------------------- run screen
    def confirm(self, chosen) -> bool:
        h, w = self.scr.getmaxyx()
        dry = " (DRY-RUN)" if self.ctx.dry_run else ""
        self.put(h - 2, 0, " " * (w - 1))
        self.put(h - 2, 1, f"Run {len(chosen)} step(s){dry}? [y/N]", self.C_WARN | curses.A_BOLD)
        self.scr.refresh()
        return self.scr.getch() in (ord("y"), ord("Y"))

    def prepare_sudo(self, chosen) -> bool:
        if self.ctx.dry_run or os.geteuid() == 0 or not any(s.needs_sudo(self.ctx) for _, s in chosen):
            return True
        if subprocess.call(["sudo", "-n", "true"], stderr=subprocess.DEVNULL) == 0:
            return True
        self.log.info("ui: leaving curses to obtain sudo credentials")
        curses.def_prog_mode()
        curses.endwin()
        print("\nSome selected steps need administrator rights. Enter your password:")
        ok = subprocess.call(["sudo", "-v"]) == 0
        curses.reset_prog_mode()
        self.scr.refresh()
        self.log.info("ui: sudo -v %s", "ok" if ok else "FAILED")
        return ok

    def draw_run(self, chosen, final: bool = False, results: Optional[List[StepResult]] = None) -> None:
        self.scr.erase()
        if self.too_small():
            return
        h, w = self.scr.getmaxyx()
        dry = " [DRY-RUN]" if self.ctx.dry_run else ""
        head = f" Running{dry}"
        if final and results is not None:
            head = (f" Finished{dry}: {sum(r.status == 'ok' for r in results)} ok, "
                    f"{sum(r.status == 'failed' for r in results)} failed")
        self.put(0, 0, head, self.C_BAD | curses.A_BOLD if final and results and any(r.status == "failed" for r in results) else self.C_HEAD)
        shown = chosen[-(h // 2 - 2):] if len(chosen) > h // 2 - 2 else chosen
        for i, (m, s) in enumerate(shown):
            st = self.progress.get((m.id, s.id), "pending")
            tag, attr = {"pending": ("[ .. ]", curses.A_DIM), "running": ("[ >> ]", self.C_WARN | curses.A_BOLD),
                         "ok": ("[ ok ]", self.C_OK), "failed": ("[FAIL]", self.C_BAD | curses.A_BOLD),
                         "skipped": ("[skip]", curses.A_DIM)}[st]
            self.put(1 + i, 1, tag, attr)
            self.put(1 + i, 8, s.title)
        base = 1 + len(shown)
        self.put(base, 0, "─" * (w - 1), curses.A_DIM)
        if final and results is not None:
            lines = summarize_lines(self.ctx, results)
        else:
            lines = list(self.tail)
        room = h - base - 2
        for i, line in enumerate(lines[-room:]):
            attr = self.C_BAD if line.startswith("FAILED") else 0
            self.put(base + 1 + i, 1, line.replace("\t", "    "), attr)
        self.put(h - 1, 0, " press any key to return" if final else " running… Ctrl-C aborts", curses.A_REVERSE)
        self.scr.refresh()

    def execute(self) -> None:
        chosen = self.chosen()
        if not chosen:
            self.msg = "nothing selected"
            return
        if not self.confirm(chosen):
            self.msg = "cancelled"
            return
        self.log.info("ui: run confirmed (%d steps)", len(chosen))
        if not self.prepare_sudo(chosen):
            self.msg = "sudo authentication failed; nothing was run"
            return
        self.tail.clear()
        self.progress = {(m.id, s.id): "pending" for m, s in chosen}

        def sink(line: str) -> None:
            self.tail.append(line)
            now = time.time()
            if now - self._last_draw > 0.08:
                self._last_draw = now
                self.draw_run(chosen)

        def on_event(kind, m, s, res) -> None:
            self.progress[(m.id, s.id)] = "running" if kind == "start" else res.status
            self.tail.append(f"── {s.title}" if kind == "start" else
                             f"── {res.status}: {res.detail.splitlines()[0] if res.detail else ''}")
            self._last_draw = 0
            self.draw_run(chosen)

        self.ctx.sink = sink
        results: List[StepResult] = []
        try:
            results = run_steps(self.ctx, chosen, on_event)
        except KeyboardInterrupt:
            self.log.error("ui: run aborted by user")
            self.msg = "run aborted (Ctrl-C)"
        finally:
            self.ctx.sink = lambda line: None
        curses.flushinp()
        self.draw_run(chosen, final=True, results=results)
        self.scr.timeout(-1)
        self.scr.getch()
        self.refresh_states()

    # ---------------------------------------------------------------- main
    def _main(self, scr) -> int:
        self.scr = scr
        scr.keypad(True)
        self.init_colors()
        self.log.info("ui: started (%dx%d)", *reversed(scr.getmaxyx()))
        self.select_loop()
        return 0

    def run(self) -> int:
        return curses.wrapper(self._main)
