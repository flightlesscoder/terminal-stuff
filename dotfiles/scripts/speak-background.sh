#!/usr/bin/env bash
# speak-background.sh -- speak the given text in the background, so the caller never blocks.
#
# Usage: speak-background.sh some text to speak    (all arguments are joined into the text)
#
# Deployed to ~/apps/scripts/speak-background.sh by ./setup/setup.sh (module "speech"), and from
# there configured (voice/rate/args, muted or not) by the hub app's Speech tab -- or by hand, see
# the OPTIONS below. Never overwritten once it exists, so your edits stick.
#
# Engine: macOS uses `say`; Linux tries spd-say, then espeak-ng, then festival, then flite (first
# one found on PATH, unless SPEAK_ENGINE below forces one); Windows/WSL shells out to PowerShell's
# System.Speech.Synthesis. Bash 3.2 compatible (macOS default): no associative arrays.
set -u

# ---------------------------------------------------------------- OPTIONS (edit here, or via hub)
# Force one engine instead of auto-detecting: say | spd-say | espeak-ng | festival | flite | powershell | none
SPEAK_ENGINE=""

# Extra arguments for whichever engine ends up used, as a bash ARRAY (not a plain string) so a
# value containing spaces -- e.g. a macOS enhanced voice name like "Samantha (Enhanced)" -- is
# passed through as one argument instead of being word-split. Find voice names with `say -v ?`
# (macOS) or `espeak-ng --voices` / `spd-say -L` (Linux). Each line's shape must stay exactly
# `NAME=(...)`, one per line -- that's what the hub app's editor looks for.
SAY_ARGS=(-v "Allison (Enhanced)")   # e.g.: SAY_ARGS=(-v "Samantha (Enhanced)" -r 175)
SPD_SAY_ARGS=()           # e.g.: SPD_SAY_ARGS=(-r 10 -p 0 -t male1)
ESPEAK_NG_ARGS=(-s 160)   # e.g.: ESPEAK_NG_ARGS=(-v en-us+f3 -s 150)
FESTIVAL_ARGS=()          # festival reads text from stdin regardless of this
FLITE_ARGS=()             # e.g.: FLITE_ARGS=(-voice slt)
POWERSHELL_RATE=(0)       # System.Speech Rate: -10 (slow) .. 10 (fast)
POWERSHELL_VOLUME=(100)   # 0 .. 100

# ---------------------------------------------------------------- engine detection
detect_engine() {
  if [ -n "$SPEAK_ENGINE" ]; then printf '%s' "$SPEAK_ENGINE"; return; fi
  case "$(uname -s)" in
    Darwin) printf say; return ;;
    MINGW*|MSYS*|CYGWIN*)
      if command -v powershell.exe >/dev/null 2>&1 || command -v pwsh >/dev/null 2>&1; then printf powershell; return; fi ;;
  esac
  if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
    printf powershell; return    # WSL: no Linux audio, but can hand off to Windows
  fi
  for e in spd-say espeak-ng festival flite; do
    command -v "$e" >/dev/null 2>&1 && { printf '%s' "$e"; return; }
  done
  printf none
}

ENGINE=$(detect_engine)

# ---------------------------------------------------------------- the actual speak call, per engine
_speak_now() {
  local text=$1
  case "$ENGINE" in
    say)        say "${SAY_ARGS[@]}" -- "$text" ;;
    spd-say)    spd-say "${SPD_SAY_ARGS[@]}" -- "$text" ;;
    espeak-ng)  espeak-ng "${ESPEAK_NG_ARGS[@]}" -- "$text" ;;
    festival)   printf '%s' "$text" | festival --tts "${FESTIVAL_ARGS[@]}" ;;
    flite)      printf '%s' "$text" | flite "${FLITE_ARGS[@]}" ;;
    powershell)
      ps=$(command -v powershell.exe || command -v pwsh)
      escaped=$(printf '%s' "$text" | sed "s/'/''/g")
      "$ps" -NoProfile -NonInteractive -Command \
        "Add-Type -AssemblyName System.Speech; \$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; \$s.Rate = ${POWERSHELL_RATE[0]}; \$s.Volume = ${POWERSHELL_VOLUME[0]}; \$s.Speak('$escaped')"
      ;;
    none|*)     echo "speak-background.sh: no speech engine found (install spd-say/espeak-ng/festival/flite, or set SPEAK_ENGINE)" >&2 ;;
  esac
}

TEXT="$*"
[ -n "$TEXT" ] || exit 0

# SPEAK-LINE: this exact line is what the hub app's Speech tab (or you, by hand) comments/
# uncomments to mute/unmute. Muted is a harmless no-op: the script still runs, it just won't speak.
_speak_now "$TEXT" &
