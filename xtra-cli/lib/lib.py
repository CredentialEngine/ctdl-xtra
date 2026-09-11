"""Shared helpers for generating and checking a Course pack."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
CLI_ROOT = HERE.parent
ROOT = CLI_ROOT.parent
SCHEMA_SRC = (HERE / "record.schema.json").absolute()


def college_slug(url: str) -> str:
    """Hostname → folder slug. Kept here so run.py can pick --out before importing the engine."""
    host = (urlparse(url).hostname or "catalog").lower()
    for prefix in ("catalog.", "www.", "coursecatalog.", "bulletin."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    if host.endswith(".edu"):
        host = host[:-4]
    elif host.endswith(".org"):
        host = host[:-4]
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    return slug or "college"


def configure(pack: Path) -> None:
    """Point the engine at this pack before freeze/build/college_capture import."""
    pack = Path(pack).expanduser().absolute()
    os.environ["XTRA_PACK"] = str(pack)
    os.environ["XTRA_SLOTS"] = "dynamic"
    os.environ["XTRA_MODE"] = "college"
    if not (os.environ.get("XTRA_PILE") or os.environ.get("GOLDEN_SET_PILE") or "").strip():
        os.environ["XTRA_PILE"] = pack.name
    pack.mkdir(parents=True, exist_ok=True)
    if SCHEMA_SRC.is_file():
        shutil.copyfile(SCHEMA_SRC, pack / "record.schema.json")
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import config

    config.bind_runtime_paths()


def load_url_file(path: Path) -> list[str]:
    """One catalog or course URL per line. Blank lines and # comments skipped."""
    path = Path(path).expanduser()
    if not path.is_file() and not path.is_absolute():
        alt = (HERE / path).absolute()
        if alt.is_file():
            path = alt
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line.split()[0])
    return urls


def pack_home() -> Path:
    """Directory where new packs appear. Override with XTRA_HOME."""
    from config import env_get

    env = env_get("XTRA_HOME")
    if env:
        return Path(env).expanduser().absolute()
    return (CLI_ROOT / "out").absolute()


def resolve_pack(out: str | None, urls: list[str]) -> Path:
    home = pack_home()
    if out:
        pack = Path(out).expanduser()
        return pack.absolute() if pack.is_absolute() else (home / pack).absolute()
    if len(urls) == 1:
        return (home / f"{college_slug(urls[0])}_courses").absolute()
    return (home / "courses_mix").absolute()


def resolve_existing_pack(pack_arg: str) -> Path:
    pack = Path(pack_arg).expanduser()
    if pack.is_absolute():
        return pack.absolute()
    home_candidate = (pack_home() / pack).absolute()
    if home_candidate.exists():
        return home_candidate
    return home_candidate


def refuse_existing_pack(pack: Path) -> str | None:
    """Refuse to write into a directory that already has files. No name list."""
    pack = Path(pack)
    if pack.is_dir() and any(pack.iterdir()):
        return (
            f"refusing to overwrite existing pack {pack}. "
            "Pick a new --out name."
        )
    return None


def json_dumps(obj: dict) -> str:
    slim = {k: v for k, v in obj.items() if k != "slots"}
    return json.dumps(slim, indent=2)


def check_pack(pack: Path) -> list[str]:
    """Freeze-backed quality + schema + xTRA scoring-file shape. Never invents expected."""
    from config import env_get, env_set

    prev_mode = env_get("XTRA_MODE") or None
    env_set("XTRA_MODE", "college")
    try:
        return _check_pack_college(pack)
    finally:
        if prev_mode is None:
            os.environ.pop("XTRA_MODE", None)
        else:
            env_set("XTRA_MODE", prev_mode)


def _check_pack_college(pack: Path) -> list[str]:
    from quality import cross_check_pack
    from validate import validate_pack

    errors: list[str] = []
    if not pack.is_dir():
        return [f"missing pack directory {pack}"]
    rec_dir = pack / "records"
    course_dir = pack / "courses"
    recs = sorted(rec_dir.glob("*.json")) if rec_dir.is_dir() else []
    course_files = sorted(course_dir.glob("*.json")) if course_dir.is_dir() else []
    if not recs:
        errors.append("no records/*.json - capture did not extract any course")
    if course_files and recs and len(course_files) != len(recs):
        errors.append(f"courses/ has {len(course_files)} files but records/ has {len(recs)}")
    for path in course_files:
        row = json.loads(path.read_text(encoding="utf-8"))
        rid = row.get("id") or path.stem
        if row.get("catalogue_type") != "COURSES":
            errors.append(f"{rid}: catalogue_type must be COURSES")
        if not (row.get("source_url") or "").startswith("http"):
            errors.append(f"{rid}: missing source_url")
        exp = row.get("expected") or {}
        if "course_id" not in exp or "course_name" not in exp:
            errors.append(f"{rid}: expected needs course_id and course_name")
        if "course_credits" in exp and (
            "course_credits_min" in exp or "course_credits_max" in exp
        ):
            errors.append(f"{rid}: course_credits cannot also have min/max")
        if ("course_credits_min" in exp) != ("course_credits_max" in exp):
            errors.append(f"{rid}: printed range needs both min and max")
    errors.extend(cross_check_pack(pack))
    errors.extend(validate_pack(pack, strict_promotion=False))
    return errors


def write_check(pack: Path, errors: list[str], extra: int | None = None) -> Path:
    rec_dir = pack / "records"
    n = extra if extra is not None else (
        len(list(rec_dir.glob("*.json"))) if rec_dir.is_dir() else 0
    )
    dest = pack / "CHECK.json"
    dest.write_text(
        json.dumps({"ok": not errors, "records": n, "errors": errors}, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def write_pack_readme(pack: Path, *, seeds: list[str], errors: list[str]) -> Path:
    rec_dir = pack / "records"
    n = len(list(rec_dir.glob("*.json"))) if rec_dir.is_dir() else 0
    status = "READY_FOR_HUMAN_REVIEW" if not errors else "FAILED_CHECKS"
    lines = [
        "# Candidate Course pack",
        "",
        "Generated by `xtra-cli`. **Not human-signed.**",
        "Do not quote `--signed-only` accuracy from this pack.",
        "",
        f"- Pack: `{_display_pack(pack)}`",
        f"- Check: **{status}** (`CHECK.json`)",
        f"- Records: {n}",
        f"- Seeds: {', '.join(seeds)}",
        "",
        "## What is freeze-perfect here",
        "",
        "- Every `expected` value is copied from `cache/` (or legacy `snapshots/`) / `normalized/`",
        "- Evidence spans must equal the freeze text",
        "- A single printed credit is `course_credits` (not invented min=max)",
        "- Unknown catalog CMS families are dropped (no LLM fill)",
        "",
        "## What humans still must do",
        "",
        "1. Open each freeze next to `courses/<id>.json` and confirm every field",
        "2. Two named reviewers sign outside this toolkit (`human_signed`)",
        "3. Only then may `--signed-only` be used",
        "",
        "## Score (candidate)",
        "",
        "```bash",
        f"python3 xtra-cli/xtra_cli.py course score --reference {_display_pack(pack)} --candidate <dumps> --pile {pack.name}",
        "```",
        "",
    ]
    dest = pack / "PACK.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def _display_pack(pack: Path) -> Path:
    """Repo- or pack-home-relative. Never a machine home path."""
    pack = Path(pack)
    for root in (pack_home(), ROOT, CLI_ROOT):
        try:
            return pack.resolve().relative_to(root.resolve())
        except ValueError:
            continue
    return Path(pack.name)
