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
    from v2_import import import_v2

    from golden_datasets import extract
    from golden_datasets.context import Ctx
    from golden_datasets.storage import LocalRoot

    path = tmp_path_factory.mktemp("avc-v1") / "root"
    root = LocalRoot(path)
    ctx = Ctx(root, "avc")
    ctx.crawl_root = LocalRoot(MIRROR)  # the crawl is read where xtra-cli wrote it (approved item 21)
    extract.init(ctx)
    import_v2(ctx, str(MIRROR), None, log=lambda *a: None)
    return path
