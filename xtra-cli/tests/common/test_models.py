from __future__ import annotations

from common.models import DownloadedResource


def test_downloaded_resource_holds_key_and_bytes() -> None:
    row = DownloadedResource(key="a.json", content=b"{}")
    assert row.key == "a.json"
    assert row.content == b"{}"


def test_downloaded_resource_accepts_text() -> None:
    row = DownloadedResource(key="a.txt", content="hello")
    assert row.content == "hello"
