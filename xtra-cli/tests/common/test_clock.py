from __future__ import annotations

import os
from datetime import datetime, timezone

from common.clock import is_iso8601_utc, run_id_for_path, utc_timestamp


def test_utc_timestamp_is_iso8601_with_z() -> None:
    stamp = utc_timestamp(datetime(2026, 9, 14, 18, 12, 0, tzinfo=timezone.utc))
    assert stamp == "2026-09-14T18:12:00Z"
    assert is_iso8601_utc(stamp)


def test_utc_timestamp_now_matches_pattern() -> None:
    stamp = utc_timestamp()
    assert is_iso8601_utc(stamp)
    assert "T" in stamp
    assert stamp.endswith("Z")


def test_run_id_for_path_keeps_colons_on_posix() -> None:
    stamp = "2026-09-14T18:12:00Z"
    if os.name == "nt":
        assert run_id_for_path(stamp) == "2026-09-14T18-12-00Z"
    else:
        assert run_id_for_path(stamp) == stamp
