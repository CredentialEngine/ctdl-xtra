import pytest

azure_blob = pytest.importorskip("azure.storage.blob")

from review_ui.azure_store import (
    AzureBlobStore,
    explain_azure_error,
    parse_azure_uri,
)
from review_ui.store import open_store


def test_parse_a_real_account_uri():
    uri = parse_azure_uri(
        "azure://https://acct.blob.core.windows.net/xtra-data/catalogs/main"
    )
    assert (uri.account_url, uri.container, uri.prefix, uri.emulator) == (
        "https://acct.blob.core.windows.net",
        "xtra-data",
        "catalogs/main/",
        False,
    )


def test_parse_a_container_with_no_prefix():
    uri = parse_azure_uri("azure://https://acct.blob.core.windows.net/xtra-data")
    assert (uri.container, uri.prefix) == ("xtra-data", "")


def test_parse_an_emulator_uri_takes_the_account_from_the_path():
    uri = parse_azure_uri(
        "azure://http://127.0.0.1:10000/devstoreaccount1/xtra/pre/fix"
    )
    assert uri.account_url == "http://127.0.0.1:10000/devstoreaccount1"
    assert (uri.container, uri.prefix, uri.emulator) == ("xtra", "pre/fix/", True)


@pytest.mark.parametrize(
    "bad",
    [
        "https://acct.blob.core.windows.net/c",  # missing the azure:// wrapper
        "azure://acct.blob.core.windows.net/c",  # not a full http(s) URL
        "azure://https://acct.blob.core.windows.net/",  # no container
        "azure://http://127.0.0.1:10000/devstoreaccount1",  # emulator without a container
    ],
)
def test_bad_uris_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_azure_uri(bad)


def test_a_real_account_uses_the_default_azure_credential(monkeypatch):
    seen = {}

    class FakeCredential:
        def get_token(self, *scopes, **kwargs):  # never called: nothing is read
            raise AssertionError("no request should be made")

    def fake_default():
        seen["used"] = True
        return FakeCredential()

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", fake_default)
    store = open_store(
        "azure://https://acct.blob.core.windows.net/xtra-data/p", cache=False
    )
    assert isinstance(store, AzureBlobStore) and seen["used"]
    assert (
        store.location("a.json")
        == "azure://https://acct.blob.core.windows.net/xtra-data/p/a.json"
    )


def test_a_prefix_isolates_one_store_from_another(azure_container):
    _, root = azure_container
    left, right = open_store(f"{root}/left"), open_store(f"{root}/right")
    left.write_text("a.txt", "L")
    right.write_text("a.txt", "R")
    assert (left.read_text("a.txt"), right.read_text("a.txt")) == ("L", "R")
    assert open_store(root).list_dir("") == ["left", "right"]
    assert open_store(root).list_dir("left") == ["a.txt"]


# -- readable Azure errors ----------------------------------------------------
ROOT = "azure://https://ceteststorage.blob.core.windows.net/xtra-cli-output"


def http_error(code, status=403, message="denied"):
    from azure.core.exceptions import HttpResponseError

    exc = HttpResponseError(message=message)
    exc.error_code, exc.status_code = code, status
    return exc


def test_a_missing_blob_role_says_which_role_to_ask_for():
    text = explain_azure_error(http_error("AuthorizationPermissionMismatch"), ROOT)
    assert "no blob data role" in text and ROOT in text
    assert (
        "Storage Blob Data Contributor" in text and "Storage Blob Data Reader" in text
    )
    assert "AZURE_STORAGE_CONNECTION_STRING" in text and "az account show" in text


def test_a_firewall_block_points_at_the_network():
    text = explain_azure_error(http_error("AuthorizationFailure"), ROOT)
    assert "firewall" in text and "VPN" in text


def test_rejected_credentials_say_to_sign_in_again():
    for exc in (http_error("AuthenticationFailed", 403), http_error("", 401)):
        assert "az login" in explain_azure_error(exc, ROOT)


def test_a_wrong_container_says_to_check_the_root():
    text = explain_azure_error(http_error("ContainerNotFound", 404), ROOT)
    assert "container or account" in text and "azure://https://<account>" in text


def test_not_being_signed_in_is_explained():
    from azure.core.exceptions import ClientAuthenticationError

    assert "Not signed in" in explain_azure_error(
        ClientAuthenticationError("no token"), ROOT
    )


def test_unrelated_errors_are_left_alone():
    assert explain_azure_error(ValueError("boom"), ROOT) is None
    assert explain_azure_error(http_error("SomethingElse", 500), ROOT) is None


def test_the_request_id_is_included_for_administrators():
    class Response:
        def __init__(self):
            self.headers = {"x-ms-request-id": "abc-123"}

    exc = http_error("AuthorizationPermissionMismatch")
    exc.response = Response()
    assert "abc-123" in explain_azure_error(exc, ROOT)


def test_the_cli_prints_the_explanation_instead_of_a_traceback(tmp_path, monkeypatch):
    from review_ui import cli

    def denied(args):
        raise http_error("AuthorizationPermissionMismatch")

    monkeypatch.setattr(cli, "cmd_rules_list", denied)
    with pytest.raises(SystemExit, match="no blob data role"):
        cli.main(["rules", "list", "--root", str(tmp_path)])


def test_the_cli_still_raises_errors_it_cannot_explain(tmp_path, monkeypatch):
    from review_ui import cli

    def broken(args):
        raise ValueError("a real bug")

    monkeypatch.setattr(cli, "cmd_rules_list", broken)
    with pytest.raises(ValueError, match="a real bug"):
        cli.main(["rules", "list", "--root", str(tmp_path)])


def test_the_server_answers_with_the_explanation_not_a_500(
    crawl_root, run, extraction, monkeypatch
):
    from fastapi.testclient import TestClient

    from review_ui.api import create_app
    from review_ui.views import ExtractionView

    client = TestClient(create_app(crawl_root, run), raise_server_exceptions=False)
    cid = "cat-2026-01-01t00-00-00z"

    def denied(self, stem):
        raise http_error("AuthorizationPermissionMismatch")

    monkeypatch.setattr(ExtractionView, "page", denied)
    reply = client.get(f"/api/c/{cid}/pages/course_admj")
    assert reply.status_code == 502 and "no blob data role" in reply.json()["detail"]


# -- the emulator, reached from a container -----------------------------------------
@pytest.mark.parametrize(
    "host", ["host.containers.internal", "host.docker.internal", "azurite"]
)
def test_container_hostnames_for_the_emulator_are_recognised(host):
    uri = parse_azure_uri(f"azure://http://{host}:10000/devstoreaccount1/box/pre")
    assert uri.emulator and uri.account_url == f"http://{host}:10000/devstoreaccount1"
    assert (uri.container, uri.prefix) == ("box", "pre/")


def test_the_emulator_connection_string_points_at_wherever_the_emulator_is():
    from review_ui.azure_store import (
        AZURITE_CONNECTION_STRING,
        azurite_connection_string,
    )

    assert (
        "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
        in AZURITE_CONNECTION_STRING
    )
    moved = azurite_connection_string("http://azurite:10000/devstoreaccount1")
    assert "BlobEndpoint=http://azurite:10000/devstoreaccount1;" in moved
    assert "AccountName=devstoreaccount1" in moved


def test_a_real_account_never_gets_an_automatic_container(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "review_ui.azure_store._create_emulator_container", lambda *a: calls.append(a)
    )
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    open_store("azure://https://acct.blob.core.windows.net/xtra-data", cache=False)
    assert (
        calls == []
    )  # only the emulator's empty storage gets a container created for it
    open_store("azure://http://127.0.0.1:10000/devstoreaccount1/box", cache=False)
    assert len(calls) == 1


def test_a_missing_emulator_is_not_an_error_when_opening_the_store():
    from review_ui.azure_store import _create_emulator_container

    # nothing listens on this port; opening must not raise (a later real request will)
    _create_emulator_container(
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=a2V5;"
        "BlobEndpoint=http://127.0.0.1:9/devstoreaccount1;",
        "box",
    )
