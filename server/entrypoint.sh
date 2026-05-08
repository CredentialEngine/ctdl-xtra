#!/bin/sh
set -e

echo "Running migrations"
./node_modules/.bin/drizzle-kit migrate

export HOME=/home/pptruser
export PUPPETEER_CACHE_DIR=/home/pptruser/.cache/puppeteer

mkdir -p "$PUPPETEER_CACHE_DIR" /app/db
chown pptruser:pptruser /home/pptruser /home/pptruser/.cache "$PUPPETEER_CACHE_DIR"
chown -R pptruser:pptruser /app/db

exec runuser -u pptruser "$@"
