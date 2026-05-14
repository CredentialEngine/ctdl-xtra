#!/bin/sh
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Running migrations"
  ./node_modules/.bin/drizzle-kit migrate
fi

chown -R pptruser:pptruser /app
if [ -d /app/db ]; then
  chown -R pptruser:pptruser /app/db
fi
if [ -n "$EXTRACTION_FILES_PATH" ]; then
  mkdir -p "$EXTRACTION_FILES_PATH"
  chown -R pptruser:pptruser "$EXTRACTION_FILES_PATH"
fi

exec runuser -u pptruser "$@"
