# fzf key bindings (Ctrl-T files, Ctrl-R history, Alt-C cd) and completion.
# Sourced from ~/.zshrc by setup/ (block: terminal-stuff:fzf). Keep after oh-my-zsh.
if command -v fzf >/dev/null 2>&1; then
  if fzf --zsh >/dev/null 2>&1; then
    # fzf >= 0.48 ships its own integration
    source <(fzf --zsh)
  else
    # older fzf (e.g. Ubuntu's apt package): use the shell files the package installed
    for _d in /usr/share/doc/fzf/examples /usr/share/fzf /usr/share/fzf/shell \
              "${HOMEBREW_PREFIX:-/nonexistent}/opt/fzf/shell" "$HOME/.fzf/shell"; do
      [ -r "$_d/key-bindings.zsh" ] && source "$_d/key-bindings.zsh"
      [ -r "$_d/completion.zsh" ] && source "$_d/completion.zsh"
    done
    unset _d
  fi
fi
