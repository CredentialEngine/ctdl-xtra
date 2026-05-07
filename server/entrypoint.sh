#!/bin/sh
set -e

echo "Running migrations"
./node_modules/.bin/drizzle-kit migrate

export HOME=/home/pptruser
export PUPPETEER_CACHE_DIR=/home/pptruser/.cache/puppeteer

mkdir -p "$PUPPETEER_CACHE_DIR"
for path in /home/pptruser /app/db; do
  if [ -e "$path" ]; then
    chown -R pptruser:pptruser "$path"
  fi
done

exec runuser -u pptruser "$@"
