"""Put xtra-cli/lib on sys.path so stage scripts can import the engine."""

from __future__ import annotations

import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent
LIB = CLI_ROOT / "lib"
REPO_ROOT = CLI_ROOT.parent

if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
# Fallback only. PYTHONPATH (e.g. C:\Code\xTRA-Scoring) must win over in-repo src/.
src = REPO_ROOT / "src"
if src.is_dir() and str(src) not in sys.path:
    sys.path.append(str(src))
