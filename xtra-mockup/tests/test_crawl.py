import hashlib

from xtra.crawl import Crawler, Response
from xtra.store import PageStore

INDEX = "https://catalog.example/undergraduatecatalog/coursesofinstruction/"
PAGES = {
    "https://catalog.example/robots.txt": b"User-agent: *\nDisallow: /search/\nDisallow: /css/\n",
    INDEX: b'<html><body><a href="/undergraduatecatalog/coursesofinstruction/acct/">Accounting (ACCT)</a>'
    b'<a href="/undergraduatecatalog/coursesofinstruction/chem/">Chemistry (CHEM)</a>'
    b'<a href="/search/?P=ACCT%2020103">ACCT 20103</a></body></html>',
    INDEX + "acct/": b"<html><body>accounting</body></html>",
    INDEX + "chem/": b"<html><body>accounting</body></html>".replace(b"accounting", b"chemistry"),
    "https://registry.example/resources/ce-1": b'{"ceterms:ctid": "ce-1"}',
}


class FakeSite:
    def __init__(self, pages=PAGES):
        self.pages = dict(pages)
        self.requested: list[str] = []

    def get(self, address):
        self.requested.append(address)
        if address not in self.pages:
            return Response(address, 404, "text/html", b"not found")
        return Response(address, 200, "text/html; charset=UTF-8", self.pages[address])


def crawl(tmp_path, site, **kwargs):
    crawler = Crawler(PageStore(tmp_path / "store"), site, sleep=lambda s: None)
    return crawler.run(index_address=INDEX, subjects=("ACCT", "CHEM"), registry_record="https://registry.example/resources/ce-1", **kwargs)


def test_first_run_stores_everything_with_sidecars(tmp_path):
    site = FakeSite()
    report = crawl(tmp_path, site)
    store = PageStore(tmp_path / "store")
    assert site.requested[0].endswith("/robots.txt")  # CR1: robots.txt first
    for address, body in PAGES.items():
        fetch = store.current(address)
        assert fetch.digest == hashlib.sha256(body).hexdigest()  # CR5: named by digest
        assert store.read(fetch.digest) == body  # exact bytes
        sidecar = store.sidecar(fetch.digest)["fetches"][0]
        assert {"requested", "final", "time", "status", "contentType", "size", "digest"} <= set(sidecar)  # CR6
    assert report.subjects == {"ACCT": INDEX + "acct/", "CHEM": INDEX + "chem/"}  # CR2: from links


def test_second_run_makes_no_requests(tmp_path):
    crawl(tmp_path, FakeSite())
    again = FakeSite()
    report = crawl(tmp_path, again)
    assert again.requested == []  # CR3
    assert report.requests_made == 0


def test_never_requests_what_robots_disallows(tmp_path):
    site = FakeSite()
    crawler = Crawler(PageStore(tmp_path / "store"), site, sleep=lambda s: None)
    assert crawler.get("https://catalog.example/search/?P=ACCT%2020103") is None
    assert crawler.get("https://catalog.example/css/screen.css") is None
    assert not any("/search/" in a or "/css/" in a for a in site.requested)


def test_waits_between_requests(tmp_path):
    waits = []
    crawler = Crawler(PageStore(tmp_path / "store"), FakeSite(), sleep=waits.append, clock=lambda: 0.0)
    crawler.run(index_address=INDEX, subjects=("ACCT",), registry_record=None)
    assert waits and all(w >= 1.0 for w in waits)  # CR4


def test_refetch_is_explicit_and_never_overwrites(tmp_path):
    crawl(tmp_path, FakeSite())
    changed = FakeSite({**PAGES, INDEX + "acct/": b"<html><body>new accounting</body></html>"})
    crawl(tmp_path, changed, refetch=(INDEX + "acct/",))
    store = PageStore(tmp_path / "store")
    history = store.history(INDEX + "acct/")
    assert changed.requested == [INDEX + "acct/"]
    assert len(history) == 2 and history[0].digest != history[1].digest
    assert store.read(history[0].digest) == PAGES[INDEX + "acct/"]  # CR9: the old file stays


def test_a_failure_is_recorded_and_not_retried(tmp_path):
    pages = {k: v for k, v in PAGES.items() if not k.endswith("chem/")}
    report = crawl(tmp_path, FakeSite(pages))
    assert any(a.endswith("chem/") for a, _ in report.failed)
    again = FakeSite(pages)
    crawl(tmp_path, again)
    assert again.requested == []  # CR10: not retried silently
    assert PageStore(tmp_path / "store").history(INDEX + "chem/")[0].status == 404


def test_identical_bytes_share_one_file(tmp_path):
    store = PageStore(tmp_path / "store")
    a = store.record_success("https://a.example/", "https://a.example/", "t", 200, "text/html", b"same")
    b = store.record_success("https://b.example/", "https://b.example/", "t", 200, "text/html", b"same")
    assert a.digest == b.digest
    assert len([p for p in (tmp_path / "store" / "objects").iterdir() if not p.name.endswith(".json")]) == 1
    assert len(store.sidecar(a.digest)["fetches"]) == 2
