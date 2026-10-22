# review-ui-v2: the review app as one stateless container.
#
# It holds no crawl data, rules or reviews. Everything is read from and written to the
# storage root named by REVIEW_UI_ROOT: an Azure container (azure://https://...), or a
# folder mounted at /data for running locally.
#
#   podman build -t review-ui-v2 .
#   podman run --rm -p 8001:8001 -e REVIEW_UI_ROOT -e AZURE_STORAGE_CONNECTION_STRING review-ui-v2

# ---- 1. build the React app ---------------------------------------------------------------
FROM docker.io/library/node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- 2. the runtime image -------------------------------------------------------------------
FROM docker.io/library/python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./
COPY server/review_ui ./server/review_ui
RUN pip install --root-user-action=ignore ".[azure]"

COPY --from=web /web/dist ./web/dist
# The field template is shipped only so a fresh storage root can be seeded:
#   review-ui-v2 template publish /app/templates/course.properties.json
COPY templates ./templates

# Run as an unprivileged user. /data is a local-folder storage root (optional); /cache holds
# the page cache for Azure roots.
RUN useradd --uid 10001 --user-group --home-dir /home/app --create-home app \
    && mkdir -p /data /cache \
    && chown -R app:app /data /cache

ENV REVIEW_UI_ROOT=/data \
    REVIEW_UI_WEB_DIST=/app/web/dist \
    REVIEW_UI_CACHE_DIR=/cache \
    REVIEW_UI_HOST=0.0.0.0 \
    REVIEW_UI_PORT=8001

USER app
EXPOSE 8001

# Liveness only: /healthz touches no storage, so a slow Azure never restarts the container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('REVIEW_UI_PORT', '8001'), timeout=4)"]

# The command is the app's own CLI, so the same image also runs the batch jobs:
#   podman run --rm ... review-ui-v2 extract --run ccsf
ENTRYPOINT ["review-ui-v2"]
CMD ["serve"]
