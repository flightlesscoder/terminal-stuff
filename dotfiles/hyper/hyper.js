// Hyper config template, installed to ~/.hyper.js by setup/ ONLY if that file doesn't exist.
// Placeholders in double underscores (shell path, font stack) are filled in at setup time.
'use strict';

module.exports = {
  config: {
    // We run the canary build for sixel support (see setup/, module terminal-env, step
    // hyper-install) -- disabled so it can never silently self-update to a "newer" stable
    // release, which would lose sixel (canary is ahead of stable only on this one feature; see
    // the comment above hyper_install in setup/tui/modules/terminal_env.py for why).
    disableAutoUpdates: true,
    updateChannel: 'stable',
    fontSize: 13,
    fontFamily: '__FONT_FAMILY__',
    cursorShape: 'BLOCK',
    cursorBlink: false,
    copyOnSelect: false,
    shell: '__ZSH__',
    shellArgs: ['--login'],
    env: {},
    bell: false,
  },
  plugins: [],
  localPlugins: [],
  keymaps: {},
};
