# oh-my-zsh. Sourced from ~/.zshrc by setup/ (block: terminal-stuff:omz).
export ZSH="${ZSH:-$HOME/.oh-my-zsh}"
ZSH_THEME=""            # the prompt comes from pure (see pure.zsh)
plugins=(git)
[ -r "$ZSH/oh-my-zsh.sh" ] && source "$ZSH/oh-my-zsh.sh"
