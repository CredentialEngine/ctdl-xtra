from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


def test_running_the_package_starts_the_cli(monkeypatch, capsys) -> None:
    """In process, so coverage sees __main__.py; the test below does not."""
    monkeypatch.setattr(sys, "argv", ["xtra", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_module("xtra", run_name="__main__")

    assert exited.value.code == 0
    assert "catalog" in capsys.readouterr().out


def test_python_m_xtra_help() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-m", "xtra", "--help"],
        cwd=str(SRC.parent),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "catalog" in proc.stdout
    assert "crawl" in proc.stdout
