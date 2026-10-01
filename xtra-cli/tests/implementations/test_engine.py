from __future__ import annotations

from pathlib import Path

from implementations.engine import load_engine


def test_load_engine_puts_lib_on_path() -> None:
    lib = load_engine()
    assert lib.name == "lib"
    assert (lib / "mapping.py").is_file()
    assert (lib / "templates" / "clean_catalog.py").is_file()
    import mapping
    import transcribe_courses

    assert Path(mapping.__file__).resolve().parent == lib
    assert hasattr(transcribe_courses, "extract_course")


def test_load_engine_is_idempotent() -> None:
    first = load_engine()
    second = load_engine()
    assert first == second
