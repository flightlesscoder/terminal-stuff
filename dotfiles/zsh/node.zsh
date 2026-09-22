# Node version management (tj/n on Linux/macOS/WSL) + npm global installs. Sourced from ~/.zshrc
# by setup/ (block: terminal-stuff:node-env). The "node" setup module installs n itself; this
# file only wires up env vars + PATH so a fresh shell finds whatever it installed.
export N_PREFIX="$HOME/apps/n-prefix"
export NPM_CONFIG_PREFIX="$HOME/apps/npm-prefix"
for _d in "$NPM_CONFIG_PREFIX/bin" "$NPM_CONFIG_PREFIX" "$N_PREFIX" "$N_PREFIX/bin"; do
  case ":$PATH:" in *":$_d:"*) ;; *) PATH="$_d:$PATH" ;; esac
done
unset _d
export PATH
