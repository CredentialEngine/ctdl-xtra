#!/bin/sh
set -e

export HOME=/home/pptruser
export PUPPETEER_CACHE_DIR=/home/pptruser/.cache/puppeteer

mkdir -p "$PUPPETEER_CACHE_DIR" /app/db
chown pptruser:pptruser /home/pptruser /home/pptruser/.cache "$PUPPETEER_CACHE_DIR"
chown -R pptruser:pptruser /app/db

if [ -n "$INSPECT_WORKERS" ]; then
  set -- "$@" --node-args="--inspect=0.0.0.0:9229"
fi

exec runuser -u pptruser -- "$@"
