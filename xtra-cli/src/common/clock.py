"""UTC timestamps. ISO8601 yyyy-MM-ddThh:mm:ssZ, not pack folders."""

from __future__ import annotations

import re
from datetime import datetime, timezone

ISO8601_UTC = "%Y-%m-%dT%H:%M:%SZ"
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PATH_SAFE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})Z$")


def utc_timestamp(moment: datetime | None = None) -> str:
    """Return UTC time as yyyy-MM-ddTHH:mm:ssZ."""
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).strftime(ISO8601_UTC)


def is_iso8601_utc(value: str) -> bool:
    """True for the colon form and for the hyphen form used in paths."""
    return bool(_ISO8601_RE.match(value) or _PATH_SAFE_RE.match(value))


def run_id_for_path(run_id: str) -> str:
    """Object-key form of a run id: hyphens, on every operating system.

    Azure blob names accept `:` and NTFS does not. Keeping the colon on
    POSIX put the same run under a different key depending on which machine
    wrote it, so Azure and local trees disagreed. The hyphen form is now
    universal and JSON metadata still carries the colon form.
    """
    return run_id.replace(":", "-")


def run_id_for_json(run_id: str) -> str:
    """ISO8601 colon form, whichever of the two forms was typed."""
    match = _PATH_SAFE_RE.match(run_id)
    if not match:
        return run_id
    day, hour, minute, second = match.groups()
    return f"{day}T{hour}:{minute}:{second}Z"
