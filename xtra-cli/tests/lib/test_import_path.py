"""src/lib/ resolves where the engine bridge puts it, and nothing shadows it."""

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
    """src/ and tests/ come first on sys.path, so a same-named module wins.

    The src/lib/ and tests/lib/ folders have no __init__.py, so from src/ and
    tests/ each is only a namespace portion, and a namespace portion loses to
    lib/lib.py once src/lib/ is on sys.path: the first test above imports lib
    to prove it. pytest names the test files tests.lib.*, never lib.*, as long
    as consider_namespace_packages stays off.
    """
    lib_names = importable_names(lib_dir)
    assert lib_names & importable_names(TESTS) == set()
    assert lib_names & importable_names(CLI_ROOT / "src") == set()


def test_every_module_finds_the_cli_root_two_levels_above_lib(
    lib_dir: Path,
) -> None:
    """Modules that work the CLI root out from their own file climb past src/."""
    import config

    import lib

    assert lib_dir == CLI_ROOT / "src" / "lib"
    assert config.CLI_ROOT == lib.CLI_ROOT == CLI_ROOT
