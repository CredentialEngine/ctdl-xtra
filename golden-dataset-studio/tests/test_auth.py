"""Shared password: hashing, the session cookie, and which routes it guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from golden_datasets.server import auth
from golden_datasets.server.app import create_app


def test_hash_is_salted_and_verifies():
    a, b = auth.hash_password("s3cret"), auth.hash_password("s3cret")
    assert a != b and "s3cret" not in a  # a new salt each time
    assert auth.verify_password("s3cret", a) and auth.verify_password("s3cret", b)
    assert not auth.verify_password("S3cret", a)
    assert not auth.verify_password("s3cret", "garbage")


def test_no_password_leaves_the_api_open(tmp_path, monkeypatch):
    monkeypatch.delenv(auth.ENV_PASSWORD, raising=False)
    monkeypatch.delenv(auth.ENV_HASH, raising=False)
    c = TestClient(create_app(str(tmp_path)))
    assert c.get("/api/session").json() == {"password_required": False, "signed_in": True}
    assert c.get("/api/profiles").status_code == 200


@pytest.mark.parametrize("env", [auth.ENV_PASSWORD, auth.ENV_HASH])
def test_password_guards_the_api(tmp_path, monkeypatch, env):
    monkeypatch.delenv(auth.ENV_PASSWORD, raising=False)
    monkeypatch.delenv(auth.ENV_HASH, raising=False)
    monkeypatch.setenv(env, "pw-1" if env == auth.ENV_PASSWORD else auth.hash_password("pw-1"))  # restarts reuse it
    c = TestClient(create_app(str(tmp_path)))
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/profiles").status_code == 401
    assert c.get("/api/session").json() == {"password_required": True, "signed_in": False}
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    assert c.post("/api/login", json={"password": "pw-1"}).status_code == 200
    assert c.get("/api/profiles").status_code == 200
    # a restart with the same environment keeps the cookie valid
    c2 = TestClient(create_app(str(tmp_path)), cookies=c.cookies)
    assert c2.get("/api/profiles").status_code == 200
    c.post("/api/logout")
    assert c.get("/api/profiles").status_code == 401


def test_cookie_from_another_password_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(auth.ENV_PASSWORD, raising=False)
    monkeypatch.setenv(auth.ENV_HASH, auth.hash_password("old"))
    c = TestClient(create_app(str(tmp_path)))
    c.post("/api/login", json={"password": "old"})
    monkeypatch.setenv(auth.ENV_HASH, auth.hash_password("new"))
    c2 = TestClient(create_app(str(tmp_path)), cookies=c.cookies)
    assert c2.get("/api/profiles").status_code == 401
