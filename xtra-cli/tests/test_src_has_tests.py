"""Rohit: every file under src/ has tests/<same path>/test_<stem>.py."""

from __future__ import annotations

from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1]
SRC = CLI_ROOT / "src"
TESTS = CLI_ROOT / "tests"


def test_every_src_module_has_matching_test_file() -> None:
    missing: list[str] = []
    extra_note = []
    for src in sorted(SRC.rglob("*.py")):
        rel = src.relative_to(SRC)
        expected = TESTS / rel.parent / f"test_{src.stem}.py"
        if not expected.is_file():
            missing.append(str(expected.relative_to(CLI_ROOT)))
            extra_note.append(str(rel))
    assert missing == [], (
        " each src module needs tests/<same-folders>/test_<name>.py.\n"
        "Missing:\n  "
        + "\n  ".join(f"{src} -> {test}" for src, test in zip(extra_note, missing))
    )
