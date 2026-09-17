"""Splice a reviewed premise into a catalog source without reformatting it.

The catalog sources keep one control per line, which is what makes `git diff`
readable after a change like this — the reviewer sees the handful of controls that
gained a premise, not the whole file rewritten. A `json.dump` would destroy that,
so the merge is textual and surgical instead.

It lives in `app/` rather than in the calling script because it is the one part of
the merge that can silently corrupt a versioned input, and logic worth testing
does not live in `scripts/`.
"""

from __future__ import annotations

import json
import re

from app.catalog.schemas import Presupposition

# ` }` or ` },` closing a one-line control entry.
_CLOSER = re.compile(r"\s*\},?\s*$")

# An already-spliced key, so re-running the merge replaces rather than duplicates.
_EXISTING = re.compile(r',\s*"presupposes":\s*\[.*?\](?=\s*\},?\s*$)')


def fragment(premises: list[Presupposition]) -> str:
    """The premises as the JSON text that goes on the control's line."""
    return json.dumps([p.model_dump(mode="json") for p in premises], ensure_ascii=False)


def splice(line: str, premises_json: str) -> str:
    """Put `presupposes` into one control's line, leaving every other byte alone.

    Idempotent: a line already carrying the key has it replaced, not repeated, so
    the merge can be re-run after the reviewer changes their mind about a control.
    """
    without = _EXISTING.sub("", line)
    match = _CLOSER.search(without)
    if match is None:
        raise ValueError(f"not a one-line control entry: {line!r}")
    return f'{without[: match.start()]}, "presupposes": {premises_json}{without[match.start() :]}'


def is_one_line_entry(line: str) -> bool:
    """Whether this line holds a whole control object, closing brace included.

    The catalog sources are not uniformly formatted: most keep one control per
    line, and the NIS2 source is pretty-printed one key per line. Both are valid
    JSON and neither should be reflowed to suit this script, so the merge asks
    which shape it is looking at instead of assuming.
    """
    stripped = line.strip()
    return stripped.startswith("{") and _CLOSER.search(line) is not None


def key_line(id_line: str, premises_json: str) -> str:
    """The `presupposes` key as its own line, indented like the `id` above it.

    For a pretty-printed entry, inserting a key after the id is the edit that
    changes least: JSON does not care where in the object the key sits, and the
    diff is one added line rather than a reflowed object.
    """
    indent = id_line[: len(id_line) - len(id_line.lstrip())]
    return f'{indent}"presupposes": {premises_json},'


def holds_key(line: str) -> bool:
    """Whether this line is an already-inserted `presupposes` key line."""
    return line.strip().startswith('"presupposes":')
