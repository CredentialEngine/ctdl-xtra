"""The page store: exact bytes named by their SHA-256 digest, a sidecar beside each, and a lookup
of addresses already fetched (specification section 4, CR3, CR5, CR6, CR9, CR10).

The store never overwrites. A refetch that returns different bytes adds a new file and a new line
in the address's history; the old file stays.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fetch:
    """One attempt to get one address, as remembered by the lookup."""

    requested: str
    final: str | None
    time: str
    status: int | None
    content_type: str | None
    size: int | None
    digest: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.digest is not None

    def to_json(self) -> dict:
        return {
            "requested": self.requested,
            "final": self.final,
            "time": self.time,
            "status": self.status,
            "contentType": self.content_type,
            "size": self.size,
            "digest": self.digest,
            "error": self.error,
        }

    @staticmethod
    def from_json(d: dict) -> "Fetch":
        return Fetch(
            requested=d["requested"],
            final=d.get("final"),
            time=d["time"],
            status=d.get("status"),
            content_type=d.get("contentType"),
            size=d.get("size"),
            digest=d.get("digest"),
            error=d.get("error"),
        )


class PageStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.lookup_path = self.root / "lookup.json"
        self._lookup: dict[str, list[dict]] = {}
        if self.lookup_path.exists():
            self._lookup = json.loads(self.lookup_path.read_text(encoding="utf-8"))["addresses"]

    # --- lookup -----------------------------------------------------------------------------

    def history(self, address: str) -> list[Fetch]:
        return [Fetch.from_json(d) for d in self._lookup.get(address, [])]

    def seen(self, address: str) -> bool:
        """True if the address was ever requested, successfully or not (CR3, CR10)."""
        return address in self._lookup

    def current(self, address: str) -> Fetch | None:
        """The latest successful fetch of an address, or None."""
        for fetch in reversed(self.history(address)):
            if fetch.ok:
                return fetch
        return None

    def addresses(self) -> list[str]:
        return sorted(self._lookup)

    # --- reading ----------------------------------------------------------------------------

    def read(self, digest: str) -> bytes:
        return (self.objects / digest).read_bytes()

    def sidecar(self, digest: str) -> dict:
        return json.loads((self.objects / f"{digest}.json").read_text(encoding="utf-8"))

    # --- writing ----------------------------------------------------------------------------

    def record_success(
        self,
        requested: str,
        final: str,
        time: str,
        status: int,
        content_type: str | None,
        body: bytes,
    ) -> Fetch:
        digest = hashlib.sha256(body).hexdigest()
        self.objects.mkdir(parents=True, exist_ok=True)
        target = self.objects / digest
        if not target.exists():  # identical bytes share one stored file (CR5)
            target.write_bytes(body)
        fetch = Fetch(requested, final, time, status, content_type, len(body), digest)
        sidecar_path = self.objects / f"{digest}.json"
        sidecar = (
            json.loads(sidecar_path.read_text(encoding="utf-8"))
            if sidecar_path.exists()
            else {"digest": digest, "size": len(body), "fetches": []}
        )
        sidecar["fetches"].append(
            {
                "requested": requested,
                "final": final,
                "time": time,
                "status": status,
                "contentType": content_type,
                "size": len(body),
                "digest": digest,
            }
        )
        _write_json(sidecar_path, sidecar)
        self._remember(fetch)
        return fetch

    def record_failure(self, requested: str, time: str, status: int | None, error: str) -> Fetch:
        fetch = Fetch(requested, None, time, status, None, None, None, error)
        self._remember(fetch)
        return fetch

    def _remember(self, fetch: Fetch) -> None:
        self._lookup.setdefault(fetch.requested, []).append(fetch.to_json())
        self.root.mkdir(parents=True, exist_ok=True)
        _write_json(self.lookup_path, {"addresses": self._lookup})


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
