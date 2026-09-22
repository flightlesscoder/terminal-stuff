# Misc shell environment: PATH, aliases, telemetry opt-outs, podman<->docker compatibility.
# Sourced from ~/.zshrc by setup/ (block: terminal-stuff:shell-extras).

# ~/apps/scripts: personal one-off scripts (not the tracked scripts/ dir in the repo).
[ -d "$HOME/apps/scripts" ] && case ":$PATH:" in *":$HOME/apps/scripts:"*) ;; *) PATH="$HOME/apps/scripts:$PATH" ;; esac
export PATH

# Some distros (Bazzite/Fedora, Debian/Ubuntu) only put python3 on PATH.
command -v python >/dev/null 2>&1 || { command -v python3 >/dev/null 2>&1 && alias python=python3; }

# Opt out of .NET's telemetry ping on every dotnet/nuget invocation.
export DOTNET_CLI_TELEMETRY_OPTOUT=true

# podman as a drop-in docker: alias the CLI, and point docker-compatible tools at podman's
# rootless socket. Needs `systemctl --user enable --now podman.socket` once per machine for the
# socket to actually exist -- this file only sets the env var, it doesn't manage the unit.
if command -v podman >/dev/null 2>&1; then
  alias docker=podman
  export DOCKER_HOST="unix://${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/podman/podman.sock"
fi
