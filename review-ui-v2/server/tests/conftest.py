import json
import shutil
from pathlib import Path

import pytest

from review_ui.rules import load_ruleset
from review_ui.rulesets import ruleset_key
from review_ui.runs import find_runs
from review_ui.store import LocalStore, open_store
from review_ui.template import TEMPLATE_KEY, load_properties

PROJECT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
RULES = FIXTURES / "rulesets" / "ccsf-curricunet-com-catalog" / "rules.json"
PROPERTIES = PROJECT / "templates" / "course.properties.json"

PAGES = [
    "course_admj",
    "course_mixed",
    "program_vmd",
    "index_courses",
    "info_policy",
]


def fixture_html(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text("utf-8")


def fixture_url(name: str) -> str:
    return json.loads((FIXTURES / f"{name}.meta.json").read_text())["final_url"]


@pytest.fixture(autouse=True)
def _isolated_page_cache(tmp_path_factory, monkeypatch):
    """Tests never touch the real ~/.cache; Azure roots cache into a throwaway folder."""
    monkeypatch.setenv(
        "REVIEW_UI_CACHE_DIR", str(tmp_path_factory.mktemp("page-cache"))
    )
    monkeypatch.delenv("REVIEW_UI_CACHE", raising=False)


def seed_template(root) -> None:
    """Publish the field template into a storage root (a folder, azure:// URI, or Store)."""
    open_store(root).write_json(TEMPLATE_KEY, json.loads(PROPERTIES.read_text()))


def publish_rules(root, source=RULES, **changes) -> dict:
    """Publish a ruleset (default: the CCSF one) into a storage root; returns it."""
    ruleset = json.loads(Path(source).read_text())
    ruleset.update(changes)
    open_store(root).write_json(ruleset_key(ruleset["catalog_folder"]), ruleset)
    return ruleset


@pytest.fixture
def properties():
    return load_properties(PROPERTIES)


@pytest.fixture
def ruleset(properties):
    return load_ruleset(RULES, {p.name for p in properties})


@pytest.fixture
def crawl_root(tmp_path):
    """A storage root holding one crawl run built from the real-page fixtures."""
    run = tmp_path / "cat" / "cat" / "2026-01-01T00-00-00Z"
    pages = run / "pages"
    pages.mkdir(parents=True)
    (run / "crawl.json").write_text(
        json.dumps(
            {
                "catalog_folder": "cat",
                "run_id": "2026-01-01T00:00:00Z",
                "seed_url": "https://ccsf.curricunet.com/catalog/",
            }
        )
    )
    for name in PAGES:
        shutil.copy(FIXTURES / f"{name}.html", pages / f"{name}.html")
        shutil.copy(FIXTURES / f"{name}.meta.json", pages / f"{name}.meta.json")
    seed_template(tmp_path)
    return tmp_path


@pytest.fixture
def store(crawl_root):
    return LocalStore(crawl_root)


@pytest.fixture
def run(crawl_root):
    return find_runs(crawl_root)[0]


SAMPLE_STEMS = ["course_admj", "course_mixed", "index_courses"]


@pytest.fixture
def extraction(crawl_root, store, run, ruleset, properties):
    """Extract the fake run with a three-page review sample; returns the report."""
    from review_ui.extract import run_extraction

    store.write_json(
        f"{run.key}/review-ui/sample.json",
        {
            "pages": [
                {"stem": s, "url": fixture_url(s), "page_type": "x", "reason": ""}
                for s in SAMPLE_STEMS
            ]
        },
    )
    return run_extraction(
        crawl_root, run, ruleset, properties, ts="2026-02-01T00-00-00Z", workers=1
    )


def build_run(base: Path, rel: str, catalog_folder: str, run_id: str) -> Path:
    """Write a fake crawl run (the fixture pages) at ``base/rel``; returns its directory."""
    run_dir = base / rel
    (run_dir / "pages").mkdir(parents=True)
    (run_dir / "crawl.json").write_text(
        json.dumps(
            {
                "catalog_folder": catalog_folder,
                "run_id": run_id,
                "seed_url": f"https://{catalog_folder}.example.edu/catalog/",
            }
        )
    )
    for name in PAGES:
        shutil.copy(FIXTURES / f"{name}.html", run_dir / "pages" / f"{name}.html")
        shutil.copy(
            FIXTURES / f"{name}.meta.json", run_dir / "pages" / f"{name}.meta.json"
        )
    return run_dir


# -- Azure Blob Storage, through the Azurite emulator --------------------------
# Run `npx azurite --blobPort 10000 --skipApiVersionCheck` (or the Azurite container)
# and these tests run; without it they are skipped, not failed.
AZURITE_BLOB = "http://127.0.0.1:10000/devstoreaccount1"


_azurite_up: bool | None = None  # checked once: every skipped test would otherwise wait


@pytest.fixture(scope="session")
def azurite():
    global _azurite_up
    blob = pytest.importorskip("azure.storage.blob")
    from azure.core.exceptions import AzureError

    from review_ui.azure_store import AZURITE_CONNECTION_STRING

    if _azurite_up is False:
        pytest.skip(
            "Azurite is not running on 127.0.0.1:10000 (npx azurite --blobPort 10000)"
        )
    # No retries and a short timeout: an absent emulator should fail in a second, not a minute.
    service = blob.BlobServiceClient.from_connection_string(
        AZURITE_CONNECTION_STRING, retry_total=0, connection_timeout=1
    )
    try:
        service.get_service_properties(timeout=2)
    except AzureError:
        _azurite_up = False
        pytest.skip(
            "Azurite is not running on 127.0.0.1:10000 (npx azurite --blobPort 10000)"
        )
    _azurite_up = True
    return service


@pytest.fixture
def azure_container(azurite):
    """A fresh, empty container in Azurite; returns (container name, azure:// root URI)."""
    import uuid

    name = f"t{uuid.uuid4().hex[:24]}"
    azurite.create_container(name)
    yield name, f"azure://{AZURITE_BLOB}/{name}"
    azurite.delete_container(name)


def upload_tree(root_uri: str, local_dir: Path) -> None:
    """Copy every file under ``local_dir`` into the Azure root, keeping relative paths."""
    from review_ui.store import open_store

    store = open_store(root_uri)
    for path in sorted(local_dir.rglob("*")):
        if path.is_file():
            store.write_text(
                path.relative_to(local_dir).as_posix(), path.read_text("utf-8")
            )
