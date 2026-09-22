# Config

JSON with `//` and `/* */` comments (JSONC), used by the setup TUI, `doctor.sh`, and the hub app.
Parsed identically by `setup/tui/jsonc.py` (Python) and `apps/hub/Jsonc.cs` (C#) -- if you change
one, change the other.

## Search order and merge

Three files are looked for, lowest priority first, and merged in that order:

1. `config/default.jsonc` (this directory) -- tracked, ships with the repo, always valid. Don't
   edit it for personal changes.
2. `~/.config/terminal-stuff/config.jsonc` -- your machine's config. `./setup/setup.sh` creates
   this from the default the first time nothing exists yet (module `config`, step `config-init`).
3. `./.terminal-stuff.jsonc` -- optional, in whatever directory a tool is run from. For a
   project-specific tweak; most people will never need this one.

Merging: object keys merge recursively (a key in a higher-priority file overrides the same key
lower down); **arrays are concatenated**, not replaced -- that's how the `paths` list in
`default.jsonc` is "extended" rather than needing to be copied in full into your own config. If
you genuinely want to remove one of the default entries, copy `default.jsonc` in full into
`~/.config/terminal-stuff/config.jsonc` and edit it there (once your file exists, it's the actual
top layer people usually reach for, so there's no separate "delete" syntax).

`${REPO}` and `${HOME}` are substituted in every string value after merging, so paths stay
portable across machines and repo clone locations.

**Replacing instead of extending an array:** write `{"$replace": [...]}` in place of a plain
array. Used for anything where order+membership together are the point, so "append" can't
express an edit -- e.g. the hub app's Status Segments tab always writes tmux's `statusLeft` /
`statusRight` this way. `./setup/setup.sh` creates `~/.config/terminal-stuff/config.jsonc` from
`config/user-template.jsonc` (empty arrays + comments explaining this), not from
`config/default.jsonc` -- copying the defaults' own already-populated arrays into your file would
double every entry the moment they're merged.

## Checking it

```sh
./setup/doctor.sh              # "config" line: present + parseable, or a hint to fix it
./setup/setup.sh --list        # module "config": config-init / config-verify steps
```

`config-verify` resolves starting from the current directory (so it also exercises a
`./.terminal-stuff.jsonc` if one is there), same as the hub app does when it starts.
