"""Module registry. Add a new module by creating modules/<name>.py with build() -> Module."""
from __future__ import annotations

from typing import List

from ..core import Module
from . import config, extras, hub, kitty, lazyvim_dev, neovim, node, obsidian, speech, terminal_env, tmux


def load_all() -> List[Module]:
    # config first: other modules' steps don't depend on it yet, but it's cheap and foundational.
    # lazyvim_dev after neovim: its steps assume neovim's LazyVim install already exists.
    return [config.build(), terminal_env.build(), tmux.build(), hub.build(), neovim.build(),
            node.build(), extras.build(), speech.build(), kitty.build(), lazyvim_dev.build(),
            obsidian.build()]
