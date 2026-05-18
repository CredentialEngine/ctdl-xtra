#!/bin/sh
set -e

chown -R pptruser:pptruser /app
if [ -d /app/db ]; then
  chown -R pptruser:pptruser /app/db
fi
if [ -n "$EXTRACTION_FILES_PATH" ]; then
  mkdir -p "$EXTRACTION_FILES_PATH"
  chown -R pptruser:pptruser "$EXTRACTION_FILES_PATH"
fi

exec runuser -u pptruser "$@"
