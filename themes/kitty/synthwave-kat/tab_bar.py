# Synthwave Kat's tab bar: kitty's own powerline renderer (kept -- see kitty.conf's
# tab_powerline_style for the actual shape), plus a right-aligned clock on the last tab and a
# glyph prefix on the first. Technique from kitty discussion #4447. Deployed to
# ~/.config/kitty/tab_bar.py (kitty only ever looks there, not next to whatever config included
# it) by setup/'s "kitty-theme" step or the hub app's kitty theme picker.
#
# Real gotcha hit building this: draw_tab_with_powerline() reads the tab's background/foreground
# straight off screen.cursor.bg/fg at its very first line -- it expects the CALLER to have already
# set those to the tab's own active/inactive colors. Drawing the icon first without setting
# cursor.bg/fg to draw_data.tab_bg(tab)/tab_fg(tab) makes the powerline call inherit whatever we
# left cursor.bg as (e.g. the plain terminal background), and the active tab silently loses its
# highlight. Fix: always paint icon/prefix content in the tab's own colors, not the default bg.
#
# Ideas for later (not done yet): dedupe/coordinate with tmux2k's own status bar segments (same
# machine info shown twice, in two bars, is redundant) -- undecided whether that means pulling the
# same data both bars read, or having one bar defer to the other when running kitty+tmux together.
from datetime import datetime

from kitty.fast_data_types import Screen
from kitty.tab_bar import DrawData, ExtraData, TabBarData, as_rgb, draw_tab_with_powerline

CLOCK_FG = 0x00f0ff   # electric cyan, matches this palette's url_color
ICON = ' '        # nf-linux-tux


def draw_tab(draw_data: DrawData, screen: Screen, tab: TabBarData, before: int, max_tab_length: int,
             index: int, is_last: bool, extra_data: ExtraData) -> int:
    if index == 1 and screen.cursor.x == 0:
        screen.cursor.bg = as_rgb(int(draw_data.tab_bg(tab)))
        screen.cursor.fg = as_rgb(int(draw_data.tab_fg(tab)))
        screen.draw(ICON)
    end = draw_tab_with_powerline(draw_data, screen, tab, before, max_tab_length, index, is_last, extra_data)
    if is_last:
        clock = datetime.now().strftime(' %H:%M ')
        if end + len(clock) < screen.columns:
            screen.cursor.x = screen.columns - len(clock)
            screen.cursor.fg = as_rgb(CLOCK_FG)
            screen.cursor.bg = as_rgb(int(draw_data.default_bg))
            screen.draw(clock)
    return end
