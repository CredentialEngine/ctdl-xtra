"""lib/ resolves where the engine bridge puts it, and nothing shadows it."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
CLI_ROOT = TESTS.parent


def importable_names(folder: Path) -> set[str]:
    """Top-level names a sys.path entry pointing at `folder` provides."""
    return {path.stem for path in folder.glob("*.py")} | {
        path.parent.name for path in folder.glob("*/__init__.py")
    }


def test_lib_config_and_templates_import_from_the_lib_folder(
    lib_dir: Path,
) -> None:
    import config
    import templates

    import lib

    assert Path(lib.__file__).resolve() == lib_dir / "lib.py"
    assert Path(config.__file__).resolve() == lib_dir / "config.py"
    assert (
        Path(templates.__file__).resolve()
        == lib_dir / "templates" / "__init__.py"
    )


def test_the_engine_bridge_appends_lib_after_src_and_tests(
    lib_dir: Path,
) -> None:
    entries = [Path(entry).resolve() for entry in sys.path if entry]
    assert entries.index(lib_dir) > entries.index(CLI_ROOT / "src")
    assert entries.index(lib_dir) > entries.index(TESTS)


def test_nothing_in_src_or_tests_shadows_a_lib_module(lib_dir: Path) -> None:
    """src/ and tests/ come first on sys.path, so a same-named module wins."""
    lib_names = importable_names(lib_dir)
    assert lib_names & importable_names(TESTS) == set()
    assert lib_names & importable_names(CLI_ROOT / "src") == set()
