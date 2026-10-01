from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadedResource:
    key: str
    content: bytes | str
