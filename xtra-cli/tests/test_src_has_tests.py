"""Every file under src/ has tests/<same path>/test_<stem>.py.

An __init__.py that holds no code, only a docstring or nothing, has
nothing to test and needs no test file.
"""

from __future__ import annotations

import ast
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1]
SRC = CLI_ROOT / "src"
TESTS = CLI_ROOT / "tests"


def holds_no_code(path: Path) -> bool:
    """True for an __init__.py that is empty or only a docstring."""
    if path.name != "__init__.py":
        return False
    body = ast.parse(path.read_text(encoding="utf-8")).body
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body = body[1:]
    return not body


def test_every_src_module_has_matching_test_file() -> None:
    missing: list[str] = []
    extra_note = []
    for src in sorted(SRC.rglob("*.py")):
        if holds_no_code(src):
            continue
        rel = src.relative_to(SRC)
        expected = TESTS / rel.parent / f"test_{src.stem}.py"
        if not expected.is_file():
            missing.append(str(expected.relative_to(CLI_ROOT)))
            extra_note.append(str(rel))
    assert missing == [], (
        "Each src module needs tests/<same-folders>/test_<name>.py.\n"
        "Missing:\n  "
        + "\n  ".join(
            f"{src} -> {test}"
            for src, test in zip(extra_note, missing, strict=True)
        )
    )


def test_an_init_with_only_a_docstring_holds_no_code(tmp_path: Path) -> None:
    init = tmp_path / "__init__.py"
    init.write_text('"""Properties in the ceterms vocabulary."""\n')
    assert holds_no_code(init)
    init.write_text("")
    assert holds_no_code(init)


def test_an_init_with_code_needs_a_test(tmp_path: Path) -> None:
    init = tmp_path / "__init__.py"
    init.write_text('"""Doc."""\nVALUE = 1\n')
    assert not holds_no_code(init)
    module = tmp_path / "module.py"
    module.write_text("")
    assert not holds_no_code(module)
