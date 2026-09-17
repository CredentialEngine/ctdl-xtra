from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from common.clock import (
    is_iso8601_utc,
    run_id_for_json,
    run_id_for_path,
    utc_timestamp,
)
from common.keys import run_prefix

COLON = "2026-09-17T14:20:01Z"
HYPHEN = "2026-09-17T14-20-01Z"


def test_utc_timestamp_is_iso8601_with_z() -> None:
    stamp = utc_timestamp(datetime(2026, 9, 14, 18, 12, 0, tzinfo=timezone.utc))
    assert stamp == "2026-09-14T18:12:00Z"
    assert is_iso8601_utc(stamp)


def test_utc_timestamp_now_matches_pattern() -> None:
    stamp = utc_timestamp()
    assert is_iso8601_utc(stamp)
    assert "T" in stamp
    assert stamp.endswith("Z")


def test_both_run_id_forms_are_accepted() -> None:
    assert is_iso8601_utc(COLON)
    assert is_iso8601_utc(HYPHEN)
    assert not is_iso8601_utc("2026-09-17")


@pytest.mark.parametrize("os_name", ["posix", "nt"])
@pytest.mark.parametrize("typed", [COLON, HYPHEN])
def test_the_run_folder_is_the_same_on_every_operating_system(
    monkeypatch, os_name: str, typed: str
) -> None:
    """Colons used to survive on POSIX, so Azure and Windows disagreed.

    Nothing below touches pathlib, so patching os.name is safe here.
    """
    monkeypatch.setattr(os, "name", os_name)
    assert run_id_for_path(typed) == HYPHEN
    assert run_prefix("catalog-example-edu", typed) == (
        f"catalog-example-edu/{HYPHEN}"
    )


def test_json_keeps_the_colon_form_whichever_was_typed() -> None:
    assert run_id_for_json(HYPHEN) == COLON
    assert run_id_for_json(COLON) == COLON
    assert run_id_for_json("not-a-run-id") == "not-a-run-id"
