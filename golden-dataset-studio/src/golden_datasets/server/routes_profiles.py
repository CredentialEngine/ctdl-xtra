"""Profiles: who is reviewing, shared by everyone on the same root (the "Who are you?" screen).

There is no login. A profile is a name and a role (`sme`: subject matter expert, or `engineer`); the browser
remembers which one it is, and events record the name as their `author` and the role as `author_role`. The list
lives in `golden-dataset-studio/profiles.json` on the root (profiles.py), so a profile one person adds is offered to
everyone. It is written with the file's ETag, so two people adding a profile at the same moment both land.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from .. import profiles as store
from ..errors import ConflictError
from ..review import LOADER
from .state import studio

router = APIRouter(prefix="/api")
PATH, ROLES, DEFAULT, _read = store.PATH, store.ROLES, store.DEFAULT, store.read


@router.get("/profiles")
def profiles(request: Request) -> dict:
    return {"profiles": _read(studio(request).root)[0], "roles": list(ROLES)}


@router.post("/profiles")
def save_profile(request: Request, body: Annotated[dict, Body()]) -> dict:
    """Add a profile, or set the role of an existing one (names match case-insensitively)."""
    name = " ".join(str(body.get("name") or "").split())
    role = body.get("role")
    check_profile(name, role)
    root = studio(request).root
    for _ in range(5):
        saved = try_save(root, name, role)
        if saved is not None:
            return saved
    raise HTTPException(409, "profiles.json kept changing; try again")


def check_profile(name: str, role) -> None:
    if not name or len(name) > 60:
        raise HTTPException(400, "a name of 1 to 60 characters is required")
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of {', '.join(ROLES)}")


def try_save(root, name: str, role: str) -> dict | None:
    """The saved profile and the list, or None when someone else saved in between (read again and reapply)."""
    items, etag = _read(root)
    found = set_role(items, name, role)
    try:
        if etag is None:
            root.write_json(PATH, {"profiles": items}, if_none_match=True)
        else:
            root.write_json(PATH, {"profiles": items}, if_match=etag)
    except ConflictError:
        return None
    LOADER.forget_reviews()  # a role changed: whose checks are human-reviewed changes with it
    return {"profile": found, "profiles": items}


def set_role(items: list[dict], name: str, role: str) -> dict:
    found = next((p for p in items if p["name"].lower() == name.lower()), None)
    if found:
        found["role"] = role
        return found
    found = {"name": name, "role": role}
    items.append(found)
    return found
