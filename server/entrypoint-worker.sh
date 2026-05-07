#!/bin/sh
set -e

chown -R pptruser:pptruser /app
chown -R pptruser:pptruser /app/db

export HOME=/home/pptruser
export PUPPETEER_CACHE_DIR=/home/pptruser/.cache/puppeteer

if [ -n "$INSPECT_WORKERS" ]; then
  set -- "$@" --node-args="--inspect=0.0.0.0:9229"
fi

exec runuser -u pptruser -- "$@"
