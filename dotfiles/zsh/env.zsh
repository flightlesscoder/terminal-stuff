# Environment basics. Sourced from ~/.zshrc by setup/ (block: terminal-stuff:zsh-env).

# Homebrew (Linux + macOS): puts brew and brew-installed tools on PATH.
for _brew in /home/linuxbrew/.linuxbrew/bin/brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$_brew" ]; then eval "$("$_brew" shellenv)"; break; fi
done
unset _brew

[ -d "$HOME/.local/bin" ] && case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac
export PATH
