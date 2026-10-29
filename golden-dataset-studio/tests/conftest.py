"""Shared fixtures. `avc_v1_root` builds AVC at ruleset v1 (rs-0001, Jared's 153 imported annotations) from the
read-only mirror once per test session, so slow tests never depend on the state of `.data/`."""

from __future__ import annotations

from pathlib import Path

import pytest

MIRROR = Path.home() / "review-ui-v3-data" / "xtra-cli-output"
AVC = "avc-elumenapp-com-catalog-2026-27-welcome"


@pytest.fixture(scope="session")
def avc_v1_root(tmp_path_factory) -> Path:
    if not (MIRROR / AVC).exists():
        pytest.skip("local mirror not available")
    from golden_datasets import extract
    from golden_datasets.context import Ctx
    from golden_datasets.import_v2 import import_v2
    from golden_datasets.storage import LocalRoot
    from golden_datasets.sync import sync_catalog

    path = tmp_path_factory.mktemp("avc-v1") / "root"
    root = LocalRoot(path)
    sync_catalog(LocalRoot(MIRROR), root, AVC, None, "link", False, False)
    ctx = Ctx(root, "avc")
    extract.init(ctx)
    import_v2(ctx, str(MIRROR), None, log=lambda *a: None)
    return path
