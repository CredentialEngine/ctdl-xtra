"""Profiles API: the default list, adding a profile, setting a role, and validation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from golden_datasets.server.app import create_app


def test_profiles_default_add_and_set_role(tmp_path):
    c = TestClient(create_app(str(tmp_path)))
    d = c.get("/api/profiles").json()
    assert [p["name"] for p in d["profiles"]] == ["Jared", "Cadence", "Nicholas", "Rohit", "Eric", "Seth"]
    assert d["roles"] == ["sme", "engineer"] and all(p["role"] is None for p in d["profiles"])
    r = c.post("/api/profiles", json={"name": "jared", "role": "sme"}).json()
    assert r["profile"] == {"name": "Jared", "role": "sme"}  # matched case-insensitively, name kept
    c.post("/api/profiles", json={"name": "  Ana   Lopez ", "role": "engineer"})
    names = {p["name"]: p["role"] for p in c.get("/api/profiles").json()["profiles"]}
    assert names["Jared"] == "sme" and names["Ana Lopez"] == "engineer" and len(names) == 7
    assert (tmp_path / "golden-dataset-studio" / "profiles.json").exists()
    assert c.post("/api/profiles", json={"name": "X", "role": "boss"}).status_code == 400
    assert c.post("/api/profiles", json={"name": " ", "role": "sme"}).status_code == 400
