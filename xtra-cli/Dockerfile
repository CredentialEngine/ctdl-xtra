# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim-bookworm

# Chromium by default. For Chrome as well:
# --build-arg PLAYWRIGHT_BROWSERS="chromium chrome"
ARG PLAYWRIGHT_BROWSERS="chromium"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

# Editable on purpose: implementations/engine.py puts src/lib/ on sys.path,
# and src/lib/ is not in the wheel, so `pip install .` cannot start the CLI.
# Browsers go to PLAYWRIGHT_BROWSERS_PATH so the runtime user sees them.
## libatomic1 is for the Node.js, cannot build without it
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[azure]" \
    && python -m playwright install \
        --with-deps \
        --only-shell \
        ${PLAYWRIGHT_BROWSERS} \
    && rm -rf /var/lib/apt/lists/*

# A home for ~/.xtra/config.json, and a writable directory for relative
# targets such as --target-uri ./xtra-cache or a mounted volume.
RUN useradd --uid 1001 --gid 0 --create-home --home-dir /home/xtra xtra \
    && install -d -o 1001 -g 0 -m 775 /data

USER 1001
WORKDIR /data

# Fail the build, not the first crawl, when src/lib/ cannot be imported or
# a browser the image carries does not start. Each one is started the way
# the crawler starts it, with no fallback from one to the other.
RUN xtra --version && python - <<'PY'
import os

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    for name in os.environ["PLAYWRIGHT_BROWSERS"].split():
        if name == "chrome":
            browser = playwright.chromium.launch(channel="chrome")
        else:
            browser = playwright.chromium.launch()
        print(name, browser.version)
        browser.close()
PY

ENTRYPOINT ["xtra"]
