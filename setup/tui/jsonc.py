"""JSON-with-comments: parsing, layered search/merge, and token substitution.

Shared contract with apps/hub/Jsonc.cs (C#) -- if you change behavior here, mirror it there and
vice versa, since both must resolve the same files to the same result. See config/README.md for
the on-disk format this implements: search order, merge rule, ${TOKEN} substitution.

This module has no dependency on Ctx (unlike the rest of setup/tui/) so it can be imported
standalone, e.g. `python3 -m tui.jsonc_cli` from doctor.sh without booting the whole TUI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Tuple

CONFIG_FILENAME = "config.jsonc"
LOCAL_FILENAME = ".terminal-stuff.jsonc"


class JsoncError(Exception):
    """A config file exists but isn't valid JSONC, or a merge produced an invalid shape."""


def strip_comments(text: str) -> str:
    """Remove // and /* */ comments and trailing commas, respecting strings. Not a full tokenizer:
    good enough for hand-written config files, not for arbitrary untrusted JSON-like input."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(c)
        i += 1
    without_comments = "".join(out)
    # trailing commas: ",  }" / ",  ]" (only outside strings, which is now safe since we know
    # this pass runs after comment-stripping and strings still contain their own content verbatim)
    result, i, n = [], 0, len(without_comments)
    in_str = False
    while i < n:
        c = without_comments[i]
        if in_str:
            result.append(c)
            if c == "\\" and i + 1 < n:
                result.append(without_comments[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            result.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and without_comments[j] in " \t\r\n":
                j += 1
            if j < n and without_comments[j] in "}]":
                i += 1
                continue
        result.append(c)
        i += 1
    return "".join(result)


def loads(text: str) -> Any:
    try:
        return json.loads(strip_comments(text))
    except json.JSONDecodeError as e:
        raise JsoncError(f"{e.msg} at line {e.lineno} column {e.colno}") from e


def load_file(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise JsoncError(f"can't read {path}: {e}") from e
    try:
        return loads(text)
    except JsoncError as e:
        raise JsoncError(f"{path}: {e}") from e


REPLACE_KEY = "$replace"


def deep_merge(base: Any, override: Any) -> Any:
    """dict: recurse key by key. list: base's items followed by override's (== "extend") -- unless
    override is {"$replace": [...]}, which replaces the whole value instead (for a field like tmux
    segments where order+membership together are the point, so "append" can't express an edit).
    Anything else (scalars, or a type mismatch): override wins outright."""
    if isinstance(override, dict) and list(override.keys()) == [REPLACE_KEY]:
        return override[REPLACE_KEY]
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = deep_merge(base[k], v) if k in base else v
        return out
    if isinstance(base, list) and isinstance(override, list):
        return base + override
    return override


def substitute_tokens(value: Any, tokens: dict) -> Any:
    """Replace ${TOKEN} in every string, recursively through dicts/lists."""
    if isinstance(value, str):
        for k, v in tokens.items():
            value = value.replace("${%s}" % k, v)
        return value
    if isinstance(value, dict):
        return {k: substitute_tokens(v, tokens) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_tokens(v, tokens) for v in value]
    return value


def search_paths(repo_root: Path, cwd: Path, home: Path) -> List[Path]:
    """Lowest to highest priority -- see config/README.md. `cwd` is where "as it would load from
    the current directory" is evaluated from, so callers pass Path.cwd() or a chosen directory."""
    return [
        repo_root / "config" / "default.jsonc",
        home / ".config" / "terminal-stuff" / CONFIG_FILENAME,
        cwd / LOCAL_FILENAME,
    ]


# ------------------------------------------------------------------ targeted single-field edits
#
# Hub needs to change just tmux.statusLeft/statusRight in the user's config file without
# destroying whatever comments/formatting/other keys are already in it (a strip-comments-then-
# rewrite round trip would nuke every comment, including the ones config/user-template.jsonc
# ships with). This is text surgery on one key's value, in the same spirit as Ctx.ensure_block
# for shell configs -- not a general JSONC writer. Mirrored in apps/hub/Jsonc.cs.

def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            break
    return i


def _scan_value_span(text: str, start: int) -> Tuple[int, int]:
    """(value_start, value_end) for the JSON value beginning at or after `start`."""
    i = _skip_ws_and_comments(text, start)
    if i >= len(text):
        raise JsoncError("unexpected end of file while scanning a value")
    opener = text[i]
    if opener in "{[":
        closer = "}" if opener == "{" else "]"
        depth, j, in_str = 1, i + 1, False
        n = len(text)
        while j < n and depth:
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    in_str = False
                j += 1
                continue
            if c == '"':
                in_str = True
            elif c == "/" and j + 1 < n and text[j + 1] == "/":
                j = text.find("\n", j)
                j = n if j < 0 else j
                continue
            elif c == "/" and j + 1 < n and text[j + 1] == "*":
                e = text.find("*/", j + 2)
                j = n if e < 0 else e + 1
            elif c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
            j += 1
        if depth:
            raise JsoncError(f"unmatched '{opener}'")
        return i, j
    if opener == '"':
        j = i + 1
        while j < len(text):
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == '"':
                return i, j + 1
            j += 1
        raise JsoncError("unterminated string")
    # bare token: number / true / false / null -- ends at , } ] or whitespace/comment
    j = i
    while j < len(text) and text[j] not in ",}]\t\r\n /":
        j += 1
    return i, j


def _find_key(text: str, obj_start: int, obj_end: int, key: str) -> Tuple[int, int]:
    """(colon_index, value_start_search_from) for `"key"` at the top level of the object whose
    braces are text[obj_start] == '{' .. text[obj_end - 1] == '}'. (-1, -1) if not present."""
    i, in_str, depth = obj_start + 1, False, 0
    n = obj_end - 1
    target = f'"{key}"'
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            i = n if i < 0 or i > n else i
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            e = text.find("*/", i + 2)
            i = n if e < 0 else e + 2
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == '"':
            if depth == 0 and text.startswith(target, i):
                j = _skip_ws_and_comments(text, i + len(target))
                if j < n and text[j] == ":":
                    return j, j + 1
            in_str = True
        i += 1
    return -1, -1


def set_replace_field(text: str, key_path: List[str], new_value: Any) -> str:
    """Set (inserting parent objects/keys as needed) text[key_path...] = {"$replace": new_value},
    preserving everything else in the file byte-for-byte, comments included."""
    if not text.strip():
        text = "{}"
    root_start, root_end = _scan_value_span(text, 0)
    if text[root_start] != "{":
        raise JsoncError("top level must be an object")
    span_start, span_end = root_start, root_end
    for depth, key in enumerate(key_path):
        colon, val_start = _find_key(text, span_start, span_end, key)
        last = depth == len(key_path) - 1
        if colon < 0:
            # insert `"key": <empty object or the new value>` just before this object's closing brace
            inner_end = span_end - 1                                    # index of the '}'
            before = text[span_start + 1:inner_end]
            needs_comma = bool(before.strip())
            insertion = f'"{key}": ' + (json.dumps({REPLACE_KEY: new_value}) if last else "{}\n")
            sep = (",\n  " if needs_comma else "\n  ")
            text = text[:inner_end] + sep + insertion + ("\n" if needs_comma or before.strip() else "") + text[inner_end:]
            if last:
                return text
            # re-scan: the object we just inserted "key" into now contains a fresh {} to descend into
            colon, val_start = _find_key(text, span_start, span_end + len(sep) + len(insertion), key)
        v_start, v_end = _scan_value_span(text, val_start)
        if last:
            return text[:v_start] + json.dumps({REPLACE_KEY: new_value}) + text[v_end:]
        span_start, span_end = v_start, v_end
        if text[span_start] != "{":
            raise JsoncError(f"'{key}' is not an object; can't descend into it")
    return text


def resolve(repo_root: Path, cwd: Path, home: Path) -> Tuple[dict, List[Path]]:
    """Load+merge every existing file in search_paths(), then substitute ${REPO}/${HOME}.
    Returns (config, [paths actually used]). Raises JsoncError naming the offending file."""
    tokens = {"REPO": str(repo_root), "HOME": str(home)}
    merged: dict = {}
    used: List[Path] = []
    for p in search_paths(repo_root, cwd, home):
        if not p.is_file():
            continue
        data = load_file(p)
        if not isinstance(data, dict):
            raise JsoncError(f"{p}: top level must be a JSON object, got {type(data).__name__}")
        merged = deep_merge(merged, data)
        used.append(p)
    return substitute_tokens(merged, tokens), used
