"""The CTID service (specification section 5.4).

It knows two things: an organisation's CTID and a course code. It has one collaborator: the
ledger. It knows nothing about pages, rules, extraction or CTDL.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Callable

CTID_FORM = re.compile(r"^ce-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def normalise_code(code: str) -> str:
    """`ACCT 20103` and `ACCT  20103` are the same course code."""
    return " ".join(code.replace(" ", " ").split())


class Ledger:
    """An append-only file remembering what was minted. Entries are never changed or removed."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._entries: dict[tuple[str, str], dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._entries[(entry["organisation"], entry["code"])] = entry

    def find(self, organisation: str, code: str) -> str | None:
        entry = self._entries.get((organisation, code))
        return entry["ctid"] if entry else None

    def append(self, organisation: str, code: str, ctid: str, minted: str) -> None:
        entry = {"organisation": organisation, "code": code, "ctid": ctid, "minted": minted}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._entries[(organisation, code)] = entry

    def knows(self, ctid: str) -> bool:
        return any(e["ctid"] == ctid for e in self._entries.values())

    def entries(self) -> list[dict]:
        return list(self._entries.values())


class CtidService:
    def __init__(
        self,
        ledger: Ledger,
        new_uuid: Callable[[], str] = lambda: str(uuid.uuid4()),
        today: Callable[[], str] = lambda: date.today().isoformat(),
    ):
        self._ledger = ledger
        self._new_uuid = new_uuid
        self._today = today

    def ctid_for(self, organisation_ctid: str, course_code: str) -> str:
        """Give me the CTID for this organisation and this course code."""
        code = normalise_code(course_code)
        known = self._ledger.find(organisation_ctid, code)
        if known:
            return known
        ctid = f"ce-{self._new_uuid()}"
        self._ledger.append(organisation_ctid, code, ctid, self._today())
        return ctid
