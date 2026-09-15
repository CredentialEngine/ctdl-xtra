"""UTC timestamps. : ISO8601 yyyy-MM-ddThh:mm:ssZ, not pack folders."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

ISO8601_UTC = "%Y-%m-%dT%H:%M:%SZ"
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PATH_SAFE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")


def utc_timestamp(moment: datetime | None = None) -> str:
    """Return UTC time as yyyy-MM-ddTHH:mm:ssZ."""
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).strftime(ISO8601_UTC)


def is_iso8601_utc(value: str) -> bool:
    return bool(_ISO8601_RE.match(value) or _PATH_SAFE_RE.match(value))


def run_id_for_path(run_id: str) -> str:
    """Object-key form of a run id.

    Azure blob names accept `:`. Local Windows paths do not, so colons become
    hyphens only on Windows. JSON metadata always keeps the ISO8601 form.
    """
    if os.name == "nt":
        return run_id.replace(":", "-")
    return run_id
