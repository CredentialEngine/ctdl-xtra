# xtra-cli

Command-line ETL for public college catalog pages used by Credential Engine xTRA.

The layout follows **ceops**: Click commands live at `src/xtra/<noun>/<verb>.py`, tests at `tests/xtra/<noun>/test_<verb>.py`, and reusable storage code lives in `src/common/`. There is no pack folder and no zip of a run. Each run is identified by an ISO8601 UTC timestamp `yyyy-MM-ddTHH:mm:ssZ`.

This CLI does not invent CTIDs and does not publish to the Credential Registry.

## Install

Python 3.10+. From this directory:

```bash
python3 -m pip install -e ".[dev]"
python3 -m playwright install chrome
```

Azure Blob (production or Azurite) needs the extra:

```bash
python3 -m pip install -e ".[dev,azure]"
```

Azurite (local Azure Blob emulator), same as ceops:

```bash
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
```

## Windows

PowerShell, from the repo root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\xtra-cli[dev]"
python -m playwright install chromium

xtra --version
xtra environment set dev --data-uri .\xtra-cache
xtra catalog crawl --with-playwright --url https://catalog.brookdalecc.edu --limit 5 --discover-only --min-interval 0
```

If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
first. In `cmd.exe` the activate line is `.\.venv\Scripts\activate.bat`.

Environment variables are set per shell:

```powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "UseDevelopmentStorage=true"
$env:XTRA_ENV = "test"
$env:XTRA_CONFIG_DIR = "C:\ci\xtra-config"
$env:LOG_LEVEL = "DEBUG"
```

In `cmd.exe` use `set NAME=value`, and `setx NAME value` to persist across sessions.

Two Windows differences to expect:

- **Run folders use hyphens.** NTFS rejects `:` in a filename, so `run_id_for_path` turns
  `2026-09-15T03:27:43Z` into `2026-09-15T03-27-43Z` for the folder name. You still pass
  `--run-id` with colons and the JSON keeps the colon form, so copy the `run_id` from the
  crawl output as printed. Azure Blob accepts colons, so a Windows machine writing to
  Azure produces the same blob names as macOS.
- **The config file is not permission protected.** `save_config` calls `chmod(0o600)`,
  which on Windows only toggles the read-only bit. `%USERPROFILE%\.xtra\config.json`
  holds no secret, only the name of the variable that does, but do not treat its
  permissions as equivalent to POSIX.

Local paths work in both forms: `.\xtra-cache`, `C:\xtra-cache`, or
`file:///C:/xtra-cache`.

## Environments

An xTRA environment names *where a run is written*: the storage container and the variable holding its secret. Same verbs as `ceops environment`:

```bash
xtra environment list
xtra environment set prod --data-uri azure://https://ACCOUNT.blob.core.windows.net/xtra
xtra environment show
```

`set` saves the active environment to `~/.xtra/config.json` (`XTRA_CONFIG_DIR` relocates it for CI and containers). Only the *name* of the secret variable is stored; the connection string itself never touches disk.

`dev` is the only environment with a built-in container (Azurite at `127.0.0.1:10000`). `test`, `sandbox`, and `prod` ship blank on purpose so nobody guesses a real account name; give each one a `--data-uri` once.

Once an environment is active, the ETL commands no longer need URIs:

```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=..."
xtra catalog crawl --with-playwright --url https://catalog.brookdalecc.edu --limit 5
```

To run one command elsewhere without changing the active environment, pass `--env` (or set `XTRA_ENV`):

```bash
xtra catalog crawl --with-playwright --env sandbox --url https://catalog.brookdalecc.edu --limit 5
XTRA_ENV=test xtra catalog extract --with-template --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z
```

Resolution order for every run, highest first:

| Source | Storage URI | Azure secret |
| --- | --- | --- |
| Command flag | `--target-uri` / `--source-uri` | `--azure-storage-connection-string` |
| `--env NAME` or `XTRA_ENV` | that environment's data URI | that environment's secret variable |
| Active environment | saved data URI | saved secret variable |

An explicit URI always wins, so `--target-uri ./xtra-cache` keeps working with no environment configured at all. When nothing resolves, the command fails with the exact `xtra environment set` line to run.

Per-environment secrets in one shell, without repeated exports:

```bash
xtra environment set prod \
  --data-uri azure://https://ACCOUNT.blob.core.windows.net/xtra \
  --connection-string-env CE_PROD_STORAGE
export CE_PROD_STORAGE="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=..."
```

## Commands

Filesystem path matches invocation, the same way ceops does (`ceops elasticsearch graphs create` → `src/ceops/elasticsearch/graphs/create.py`):

```text
xtra environment set    -> src/xtra/environment.py
xtra catalog crawl      -> src/xtra/catalog/crawl.py
xtra catalog extract    -> src/xtra/catalog/extract.py
xtra catalog transform  -> src/xtra/catalog/transform.py
xtra page download      -> src/xtra/page/download.py
```

### Crawl

```bash
xtra catalog crawl --with-playwright \
  --url https://catalog.brookdalecc.edu \
  --target-uri azure://https://ACCOUNT.blob.core.windows.net/xtra \
  --limit 5 \
  --concurrency 1 \
  --min-interval 180
```

`--limit 5` caps pages for testing. Omit it for a full catalog of any size.

`--with-ai-agent` and `--with-third-party` are reserved strategy flags. They fail closed with a clear message until those backends exist. Add a backend by implementing it next to `crawl.py`; the command shape stays `xtra catalog crawl --with-<strategy>`.

Local file target (no Azure):

```bash
xtra catalog crawl --with-playwright \
  --url https://catalog.brookdalecc.edu \
  --target-uri ./xtra-cache \
  --limit 5 \
  --min-interval 0 \
  --discover-only
```

Default `--min-interval` is **180 seconds** (3 minutes) between page fetches, `--concurrency` is **1**. Failed fetches retry with exponential backoff starting at 3 minutes (3, 6, 12, … up to `--backoff-max`). That is the production posture: crawls stay up continuously across thousands of catalogs without leaning on origin sites.

### Extract and transform

Same `--with-<strategy>` pattern:

```bash
xtra catalog extract --with-template \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z

xtra catalog transform --with-ctdl \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z
```

`--with-template` is the current deterministic CMS extractors (Clean Catalog, Coursedog, Acalog). `--with-ctdl` maps printed labels to CTDL JSON-LD and never writes a CTID. `--with-ai-agent` is reserved on both verbs.

### Page download

Use when crawl ran `--discover-only` and you want to freeze HTML later, still politely:

```bash
xtra page download --with-playwright \
  --source-uri "$TARGET" --target-uri "$TARGET" \
  --catalog-id brookdalecc --run-id 2026-09-14T18:12:00Z \
  --concurrency 1 --min-interval 180
```

## Object layout (not packs)

`--target-uri` is a ceops storage URI. Runs are keys under the catalog id and the UTC timestamp:

```text
{target-uri}/{catalog-id}/{yyyy-MM-ddTHH:mm:ssZ}/
  crawl.json
  slots.json
  pages/{stem}.html
  pages/{stem}.meta.json
  pages/{stem}.txt
  records/{record-id}.json
  jsonld/{record-id}.json
  expected/{record-id}.json
```

URI schemes, copied from ceops:

```text
azure://https://account.blob.core.windows.net/container/prefix
azure://http://127.0.0.1:10000/devstoreaccount1/container/prefix   # Azurite
file:///absolute/path
./relative-path
```

Pass `--azure-storage-connection-string` or set `AZURE_STORAGE_CONNECTION_STRING`. Production reads and writes Azure Blob containers. Tests use `file://` plus mocked Blob clients; set the connection string to `UseDevelopmentStorage=true` to exercise Azurite (`pytest -m integration`).



## Tests

```bash
cd xtra-cli
python3 -m pytest tests -q
```

Network is not required. Playwright harvest is monkeypatched. Azurite tests are marked `integration` and skip unless `AZURE_STORAGE_CONNECTION_STRING` is set.

## Non-goals

- Invent `expected` values, CTIDs, or `human_signed`
- Publish to the Credential Registry
- LLM classification or extraction (the `--with-ai-agent` flags are stubs)
- Zip or pack a catalog run
