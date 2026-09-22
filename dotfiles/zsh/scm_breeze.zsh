# scm_breeze (https://github.com/scmbreeze/scm_breeze): git shortcuts, numbered file args, and
# keybindings. Sourced from ~/.zshrc by setup/ (block: terminal-stuff:scm-breeze).
#
# Skipped entirely inside a Claude Code session: its git wrapper/keybindings can error (something
# in its safe-eval helpers) when Claude shells out to git itself, not just when a human types at
# the prompt -- so new terminal/tmux sessions still get scm_breeze as normal, but a Claude Code
# session doesn't load it at all.
if [ -z "${CLAUDECODE:-}" ]; then
  [ -s "$HOME/.scm_breeze/scm_breeze.sh" ] && source "$HOME/.scm_breeze/scm_breeze.sh"
fi
