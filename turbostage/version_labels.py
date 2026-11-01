"""Recognise game versions that are not the complete game (demos, shareware).

A version counts as partial when its name contains the word "demo" or
"shareware" (e.g. "demo", "Shareware 1.4", "playable demo"). The game
database names such versions this way.
"""

import re

_PARTIAL = (
    (re.compile(r"\bdemo\b", re.IGNORECASE), "Demo", "Demo version: a short playable sample, not the complete game."),
    (
        re.compile(r"\bshareware\b", re.IGNORECASE),
        "Shareware",
        "Shareware version: the free first part of the game, not the complete version.",
    ),
)


def partial_version_label(version: str | None) -> str | None:
    """Return "Demo" or "Shareware" for an incomplete version, None for a full one."""
    for pattern, label, _note in _PARTIAL:
        if version and pattern.search(version):
            return label
    return None


def partial_version_note(version: str | None) -> str | None:
    """One sentence explaining that this version is not the complete game, or None."""
    for pattern, _label, note in _PARTIAL:
        if version and pattern.search(version):
            return note
    return None


def display_title(title: str | None, version: str | None) -> str:
    """The title shown in the library: "Doom (Shareware)" for a partial version."""
    title = title or "Unknown"
    label = partial_version_label(version)
    return f"{title} ({label})" if label else title
