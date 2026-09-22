# pure prompt (https://github.com/sindresorhus/pure). Sourced from ~/.zshrc by setup/
# (block: terminal-stuff:pure). Must come after oh-my-zsh so it wins over any theme.
if [ -r "$HOME/.zsh/pure/pure.zsh" ]; then
  fpath+=("$HOME/.zsh/pure")
  autoload -U promptinit && promptinit
  prompt pure
fi
