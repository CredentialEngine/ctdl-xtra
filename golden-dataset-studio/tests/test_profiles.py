"""Profiles API: the default list, adding a profile, setting a role, and validation."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from golden_datasets.server.app import create_app


def test_profiles_default_add_and_set_role(tmp_path):
    c = TestClient(create_app(str(tmp_path)))
    d = c.get("/api/profiles").json()
    assert [p["name"] for p in d["profiles"]] == ["Jared Diener", "Cadence Calixto", "Nicolas Soto", "Rohit Joy",
                                                    "Eric Riddoch", "Seth Alt"]
    assert d["roles"] == ["sme", "engineer"]
    assert {p["name"]: p["role"] for p in d["profiles"]} == {
        "Jared Diener": "sme", "Cadence Calixto": "sme", "Nicolas Soto": "engineer", "Rohit Joy": "engineer",
        "Eric Riddoch": "engineer", "Seth Alt": "engineer"}
    r = c.post("/api/profiles", json={"name": "seth alt", "role": "sme"}).json()
    assert r["profile"] == {"name": "Seth Alt", "role": "sme"}  # matched case-insensitively, name kept
    c.post("/api/profiles", json={"name": "  Ana   Lopez ", "role": "engineer"})
    names = {p["name"]: p["role"] for p in c.get("/api/profiles").json()["profiles"]}
    assert names["Seth Alt"] == "sme" and names["Ana Lopez"] == "engineer" and len(names) == 7
    assert (tmp_path / "golden-dataset-studio" / "profiles.json").exists()
    assert c.post("/api/profiles", json={"name": "X", "role": "boss"}).status_code == 400
    assert c.post("/api/profiles", json={"name": " ", "role": "sme"}).status_code == 400


def test_saved_first_name_profiles_get_full_names(tmp_path):
    (tmp_path / "golden-dataset-studio").mkdir()
    (tmp_path / "golden-dataset-studio" / "profiles.json").write_text(json.dumps({"profiles": [
        {"name": "Nicholas", "role": "engineer"}, {"name": "Jared", "role": "sme"}, {"name": "Ana", "role": "sme"}]}))
    c = TestClient(create_app(str(tmp_path)))
    assert [p["name"] for p in c.get("/api/profiles").json()["profiles"]] == ["Nicolas Soto", "Jared Diener", "Ana"]
