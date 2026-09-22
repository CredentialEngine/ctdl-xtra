from __future__ import annotations

import pytest

from common.polite import PoliteLimiter
from implementations.download import download_one

URL = "https://catalog.example.edu/english/engl101"


def _limiter() -> PoliteLimiter:
    return PoliteLimiter(
        concurrency=1, min_interval=0, backoff_base=0, backoff_max=0
    )


def test_download_one_normalizes_html_and_hashes() -> None:
    html = "<html><body><h1>ENGL101:</h1><p>Composition I</p></body></html>"

    def fetch(url: str):
        assert url == URL
        return html, {"http_status": 200, "requested_url": url}

    page, meta, text, stem = download_one(
        URL, limiter=_limiter(), fetch_fn=fetch, max_retries=1
    )
    assert page == html
    assert "ENGL101:" in text
    assert "Composition I" in text
    assert meta["http_status"] == 200
    assert meta["snapshot_sha256"]
    assert meta["normalized_text_sha256"]
    assert meta["stem"] == stem
    assert "engl101" in stem


def test_download_one_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def fetch(url: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("blocked")
        return "<html><body>ok</body></html>", {"http_status": 200}

    download_one(URL, limiter=_limiter(), fetch_fn=fetch, max_retries=3)
    assert calls["n"] == 2


def test_download_one_raises_after_retries() -> None:
    def fetch(url: str):
        raise RuntimeError("still blocked")

    with pytest.raises(RuntimeError, match="still blocked"):
        download_one(URL, limiter=_limiter(), fetch_fn=fetch, max_retries=2)
