"""Profiles: who is reviewing, shared by everyone on the same root (the "Who are you?" screen).

There is no login. A profile is a name and a role (`sme`: subject matter expert, or `engineer`); the browser
remembers which one it is, and events keep recording the name as their `author`. The list lives in
`golden-dataset-studio/profiles.json` on the root, so a profile one person adds is offered to everyone. It is
written with the file's ETag, so two people adding a profile at the same moment both land.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import layout
from ..errors import ConflictError
from .state import studio

router = APIRouter(prefix="/api")
PATH = f"{layout.STUDIO}/profiles.json"
ROLES = ("sme", "engineer")
DEFAULT = [("Jared Diener", "sme"), ("Cadence Calixto", "sme"), ("Nicolas Soto", "engineer"),
           ("Rohit Joy", "engineer"), ("Eric Riddoch", "engineer"), ("Seth Alt", "engineer")]
# The first defaults were first names only (and misspelled Nicolas); a saved list is read with their full names.
RENAMED = {"Jared": "Jared Diener", "Cadence": "Cadence Calixto", "Nicholas": "Nicolas Soto",
           "Rohit": "Rohit Joy", "Eric": "Eric Riddoch", "Seth": "Seth Alt"}


def _read(root) -> tuple[list[dict], str | None]:
    st = root.stat(PATH)
    if st is None:
        return [{"name": n, "role": r} for n, r in DEFAULT], None
    items = root.read_json(PATH)["profiles"]
    names = {p["name"] for p in items}
    for p in items:
        if RENAMED.get(p["name"]) not in (None, *names):
            p["name"] = RENAMED[p["name"]]
    return items, st.etag


@router.get("/profiles")
def profiles(request: Request) -> dict:
    return {"profiles": _read(studio(request).root)[0], "roles": list(ROLES)}


@router.post("/profiles")
def save_profile(request: Request, body: Annotated[dict, Body()]) -> dict:
    """Add a profile, or set the role of an existing one (names match case-insensitively)."""
    name = " ".join(str(body.get("name") or "").split())
    role = body.get("role")
    if not name or len(name) > 60:
        raise HTTPException(400, "a name of 1 to 60 characters is required")
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of {', '.join(ROLES)}")
    root = studio(request).root
    for _ in range(5):
        items, etag = _read(root)
        found = next((p for p in items if p["name"].lower() == name.lower()), None)
        if found:
            found["role"] = role
        else:
            found = {"name": name, "role": role}
            items.append(found)
        try:
            if etag is None:
                root.write_json(PATH, {"profiles": items}, if_none_match=True)
            else:
                root.write_json(PATH, {"profiles": items}, if_match=etag)
            return {"profile": found, "profiles": items}
        except ConflictError:
            continue  # someone else saved in between: read again and reapply
    raise HTTPException(409, "profiles.json kept changing; try again")
