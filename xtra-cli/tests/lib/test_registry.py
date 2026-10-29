"""The exact-URL registry lookup, with httpx2 answered in-process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
import registry
from lib_doubles import NOW, course_record
from registry import (
    SEARCH_URL,
    _api_key,
    _ctid_of,
    _post_search,
    _walk_subject_webpages,
    apply_to_record,
    lookup_pack,
    lookup_url,
)

URL = "https://catalog.example.edu/english/engl101"
CTID = "ce-1d2f3a4b-5c6d-4e7f-8a9b-0c1d2e3f4a5b"
MATCHED = {
    "ceterms:ctid": CTID,
    "ceterms:subjectWebpage": URL,
    "ceterms:name": "Composition I",
}


def serve(
    monkeypatch: pytest.MonkeyPatch, status: int = 200, body: bytes = b"{}"
) -> list[httpx2.Request]:
    """Answer every request with `status` and `body`, and record it."""
    calls: list[httpx2.Request] = []

    def handle(transport: Any, request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(status, content=body)

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", handle)
    return calls


def search_returns(
    monkeypatch: pytest.MonkeyPatch, status: int, payload: Any
) -> None:
    monkeypatch.setattr(registry, "_post_search", lambda url: (status, payload))


@pytest.mark.parametrize(
    ("env", "key"),
    [
        ({}, None),
        ({"CE_REGISTRY_API_KEY": "third"}, "third"),
        ({"CE_API_KEY": "second", "CE_REGISTRY_API_KEY": "third"}, "second"),
        ({"REGISTRY_API_KEY": "first", "CE_API_KEY": "second"}, "first"),
        ({"REGISTRY_API_KEY": "", "CE_API_KEY": "second"}, "second"),
    ],
)
def test_the_api_key_comes_from_the_first_variable_set(
    monkeypatch: pytest.MonkeyPatch, env: dict, key: str | None
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert _api_key() == key


def test_subject_webpages_are_collected_from_every_level() -> None:
    one = {"ceterms:subjectWebpage": URL}
    many = {"ceterms:subjectWebpage": [URL, "https://other.example.edu", 7]}
    hits: list = []
    _walk_subject_webpages({"data": [one, {"nested": many}]}, hits)
    assert hits == [
        (URL, one),
        (URL, one),
        ("", many),
        (URL, many),
        ("https://other.example.edu", many),
    ]


@pytest.mark.parametrize(
    ("obj", "ctid"),
    [
        ({"ceterms:ctid": CTID}, CTID),
        (
            {"@id": f"https://credentialengineregistry.org/resources/{CTID}"},
            CTID,
        ),
        ({"@id": f"https://example.org/resources/{CTID}/history"}, CTID),
        ({"ctid": "ce-short"}, "ce-short"),
        ({"ceterms:ctid": CTID, "@id": "https://example.org/r/ce-other"}, CTID),
        ({"@id": "https://example.org/no-identifier"}, None),
        ({"ceterms:ctid": 42}, None),
    ],
)
def test_the_ctid_is_the_first_39_characters_from_ce(
    obj: dict, ctid: str | None
) -> None:
    assert _ctid_of(obj) == ctid


def test_the_search_posts_one_exact_subject_webpage_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", "test-key")
    calls = serve(monkeypatch, body=b'{"data": []}')
    assert _post_search(URL) == (200, {"data": []})
    request = calls[0]
    assert str(request.url) == SEARCH_URL
    assert request.method == "POST"
    assert request.extensions["timeout"]["read"] == 45
    assert request.headers["content-type"] == "application/json"
    assert request.headers["user-agent"] == "xtra-cli/1.0"
    body = json.loads(request.content)
    assert body["Filters"] == [
        {"URI": "ceterms:subjectWebpage", "ItemTexts": [URL]}
    ]
    assert body["ExactMatch"] is True
    assert body["SearchTerms"] == ""


@pytest.mark.parametrize(
    ("key", "header"),
    [
        ("test-key", "Bearer test-key"),
        ("Bearer test-key", "Bearer test-key"),
        ("bearer test-key", "bearer test-key"),
    ],
)
def test_the_key_is_sent_as_a_bearer_token_exactly_once(
    monkeypatch: pytest.MonkeyPatch, key: str, header: str
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", key)
    calls = serve(monkeypatch)
    _post_search(URL)
    assert calls[0].headers.get_list("authorization") == [header]


def test_without_a_key_no_authorization_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = serve(monkeypatch)
    _post_search(URL)
    assert "authorization" not in calls[0].headers


def test_a_body_that_is_not_json_comes_back_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(monkeypatch, body=b"<html>maintenance</html>")
    assert _post_search(URL) == (200, "<html>maintenance</html>")


@pytest.mark.parametrize(
    ("body", "payload"),
    [(b'{"error": "unauthorized"}', {"error": "unauthorized"}), (b"No", "No")],
)
def test_an_http_error_returns_its_status_and_body(
    monkeypatch: pytest.MonkeyPatch, body: bytes, payload: Any
) -> None:
    serve(monkeypatch, status=401, body=body)
    assert _post_search(URL) == (401, payload)


def test_an_unreachable_registry_is_status_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(transport: Any, request: httpx2.Request) -> None:
        raise httpx2.ConnectError("getaddrinfo failed", request=request)

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", unreachable)
    assert _post_search(URL) == (0, {"error": "getaddrinfo failed"})


def test_without_a_key_the_lookup_is_not_checked_whatever_comes_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_returns(monkeypatch, 200, {"data": [MATCHED]})
    result = lookup_url(URL)
    assert result["decision"] == "not_checked"
    assert result["api_key_present"] is False
    assert "No name search was performed" in result["notes"]


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_key_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", "test-key")
    search_returns(monkeypatch, status, {"error": "denied"})
    assert lookup_url(URL)["decision"] == "not_checked"


def test_any_other_failure_is_not_checked_and_names_the_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", "test-key")
    search_returns(monkeypatch, 500, "upstream error")
    result = lookup_url(URL)
    assert result["decision"] == "not_checked"
    assert result["notes"].startswith("Registry search HTTP 500.")


def test_a_near_miss_url_is_not_found_even_when_the_name_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", "test-key")
    near = {**MATCHED, "ceterms:subjectWebpage": URL + "/"}
    search_returns(monkeypatch, 200, {"data": [near]})
    result = lookup_url(URL)
    assert result["decision"] == "record_not_found"
    assert result["exact_subjectWebpage_hits"] == 0
    assert "Name matching is forbidden" in result["notes"]


def test_an_exact_subject_webpage_is_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGISTRY_API_KEY", "test-key")
    search_returns(monkeypatch, 200, {"data": [MATCHED]})
    result = lookup_url(URL)
    assert result["decision"] == "matched"
    assert result["registry_ctid"] == CTID
    assert result["matched_object"] == MATCHED
    assert result["exact_subjectWebpage_hits"] == 1
    assert result["search_url"] == SEARCH_URL


@pytest.mark.parametrize(
    ("payload", "kept"),
    [("x" * 9000, "x" * 8000), ("short", "short"), ({"a": 1}, {"a": 1})],
)
def test_a_long_text_payload_is_kept_to_8000_characters(
    monkeypatch: pytest.MonkeyPatch, payload: Any, kept: Any
) -> None:
    search_returns(monkeypatch, 502, payload)
    assert lookup_url(URL)["payload"] == kept


def test_a_match_records_the_registry_resource(fixed_clock: str) -> None:
    rec: dict = {}
    lookup = {"decision": "matched", "registry_ctid": CTID, "notes": "Exact."}
    apply_to_record(rec, lookup, rel_path="registry/x.json", sha256="a" * 64)
    assert rec["registry_expected"] == {
        "status": "matched",
        "checked_at": NOW,
        "registry_ctid": CTID,
        "registry_url": (
            f"https://credentialengineregistry.org/resources/{CTID}"
        ),
        "registry_snapshot_path": "registry/x.json",
        "registry_resource_sha256": "a" * 64,
        "property_comparisons": [],
        "notes": "Exact.",
    }


def test_not_found_records_when_it_looked_but_no_resource(
    fixed_clock: str,
) -> None:
    rec: dict = {}
    lookup = {"decision": "record_not_found", "registry_ctid": CTID}
    apply_to_record(rec, lookup, rel_path="registry/x.json", sha256="a" * 64)
    expected = rec["registry_expected"]
    assert expected["checked_at"] == NOW
    assert expected["registry_ctid"] is None
    assert expected["registry_url"] is None


def test_not_checked_still_stamps_the_time_and_keeps_the_response_hash(
    fixed_clock: str,
) -> None:
    """The not_checked branch overwrites the None it first assigns."""
    rec: dict = {}
    apply_to_record(
        rec, {"decision": "not_checked"}, rel_path="r.json", sha256="b" * 64
    )
    expected = rec["registry_expected"]
    assert expected["status"] == "not_checked"
    assert expected["checked_at"] == NOW
    assert expected["registry_ctid"] is None
    assert expected["registry_resource_sha256"] == "b" * 64


def test_lookup_pack_saves_each_response_and_stamps_each_record(
    pack: Path, monkeypatch: pytest.MonkeyPatch, fixed_clock: str
) -> None:
    course_record(pack)
    seen: list[str] = []

    def lookup(url: str) -> dict:
        seen.append(url)
        return {"decision": "not_checked", "http_status": 0, "notes": "n"}

    monkeypatch.setattr(registry, "lookup_url", lookup)
    rows = lookup_pack()
    assert seen == [URL]
    assert rows == [
        {
            "record_id": "example-engl101-course",
            "decision": "not_checked",
            "http_status": 0,
        }
    ]
    saved = pack / "registry" / "example-engl101-course.json"
    rec = json.loads(
        (pack / "records" / "example-engl101-course.json").read_text(
            encoding="utf-8"
        )
    )
    expected = rec["registry_expected"]
    assert expected["registry_snapshot_path"] == (
        "registry/example-engl101-course.json"
    )
    assert expected["registry_resource_sha256"] == registry.sha256_bytes(
        saved.read_bytes()
    )
    summary = json.loads(
        (pack / "registry" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary == rows
