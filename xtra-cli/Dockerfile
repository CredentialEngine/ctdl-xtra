# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim-bookworm

# PlaywrightFetcher launches Chrome first and falls back to chromium's
# headless shell, which is all --only-shell installs of it. Google ships
# Chrome for linux/amd64 only, so build arm64 images with
# --build-arg PLAYWRIGHT_BROWSERS=chromium.
ARG PLAYWRIGHT_BROWSERS="chrome chromium"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY lib /app/lib

# Editable on purpose: implementations/engine.py puts the lib/ beside src/ on
# sys.path, and lib/ is not in the wheel, so `pip install .` cannot start the
# CLI. Browsers go to PLAYWRIGHT_BROWSERS_PATH so the runtime user sees them.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[azure]" \
    && python -m playwright install --with-deps --only-shell ${PLAYWRIGHT_BROWSERS} \
    && rm -rf /var/lib/apt/lists/*

# A home for ~/.xtra/config.json, and a writable directory for relative
# targets such as --target-uri ./xtra-cache or a mounted volume.
RUN useradd --uid 1001 --gid 0 --create-home --home-dir /home/xtra xtra \
    && install -d -o 1001 -g 0 -m 775 /data

USER 1001
WORKDIR /data

# Fail the build, not the first crawl, when lib/ cannot be imported or no
# browser starts. The launch order is the fetcher's.
RUN xtra --version && python - <<'PY'
from playwright.sync_api import Error, sync_playwright

with sync_playwright() as playwright:
    try:
        browser = playwright.chromium.launch(channel="chrome")
    except Error:
        browser = playwright.chromium.launch()
    print(browser.browser_type.name, browser.version)
    browser.close()
PY

ENTRYPOINT ["xtra"]
