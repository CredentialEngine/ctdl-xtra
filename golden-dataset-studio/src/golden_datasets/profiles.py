"""Profiles: who is reviewing, shared by everyone on the same root (the "Who are you?" screen; spec Evals §4.3).

A profile is a name and a role (`sme`: subject matter expert, or `engineer`). The list lives in
`golden-dataset-studio/profiles.json` on the root. Only an expert's verdict makes a value human-reviewed: an event
says its `author_role` since the Evals work, and older events take their author's role from this list today.
"""

from __future__ import annotations

from . import layout
from .log import FULL_NAMES as RENAMED

PATH = f"{layout.STUDIO}/profiles.json"
ROLES = ("sme", "engineer")
DEFAULT = [("Jared Diener", "sme"), ("Cadence Calixto", "sme"), ("Nicolas Soto", "engineer"),
           ("Rohit Joy", "engineer"), ("Eric Riddoch", "engineer"), ("Seth Alt", "engineer")]
# The first defaults were first names only (and misspelled Nicolas); a saved list is read with their full names.


def read(root) -> tuple[list[dict], str | None]:
    st = root.stat(PATH)
    if st is None:
        return [{"name": n, "role": r} for n, r in DEFAULT], None
    items = root.read_json(PATH)["profiles"]
    names = {p["name"] for p in items}
    for p in items:
        if RENAMED.get(p["name"]) not in (None, *names):
            p["name"] = RENAMED[p["name"]]
    return items, st.etag


def roles(root) -> dict[str, str]:
    """name → role, as profiles.json says today."""
    return {p["name"]: p["role"] for p in read(root)[0]}


def role_of(event: dict, roles: dict[str, str]) -> str | None:
    """The event's `author_role`, else its author's role today (first-name authors by their full name)."""
    return event.get("author_role") or roles.get(event["author"]) or roles.get(RENAMED.get(event["author"], ""))
