"""Every function body stays at 15 lines or fewer (docstring excluded).

The allowlist is a ratchet: functions still over the limit are listed in
``function_length_allowlist.txt`` and the list may only shrink.
"""

import ast
from pathlib import Path

MAX_LINES = 15
PACKAGE = Path(__file__).parent.parent / "src"
ALLOWLIST = Path(__file__).parent / "function_length_allowlist.txt"


def test_no_new_long_functions():
    unlisted = sorted(set(long_functions()) - allowed_functions())
    assert not unlisted, f"functions over {MAX_LINES} lines; split them:\n" + "\n".join(unlisted)


def test_allowlist_only_shrinks():
    fixed = sorted(allowed_functions() - set(long_functions()))
    assert not fixed, "now short (or gone); remove them from the allowlist:\n" + "\n".join(fixed)


def long_functions():
    return {
        name: length
        for path in sorted(PACKAGE.rglob("*.py"))
        for name, length in measure_functions(path)
        if length > MAX_LINES
    }


def allowed_functions():
    lines = (line.strip() for line in ALLOWLIST.read_text().splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def measure_functions(path):
    module = path.relative_to(PACKAGE).as_posix()
    for scope, function in walk_functions(ast.parse(path.read_text()), ""):
        yield f"{module}::{scope}{function.name}", body_length(function)


def walk_functions(node, scope):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield scope, child
            yield from walk_functions(child, f"{scope}{child.name}.")
        elif isinstance(child, ast.ClassDef):
            yield from walk_functions(child, f"{scope}{child.name}.")
        else:
            yield from walk_functions(child, scope)


def body_length(function):
    body = function.body[1:] if ast.get_docstring(function) else function.body
    return body[-1].end_lineno - body[0].lineno + 1 if body else 0
