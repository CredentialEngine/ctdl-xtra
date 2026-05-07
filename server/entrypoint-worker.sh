#!/bin/sh
set -e

export HOME=/home/pptruser
export PUPPETEER_CACHE_DIR=/home/pptruser/.cache/puppeteer

mkdir -p "$PUPPETEER_CACHE_DIR"
for path in /home/pptruser /app/db; do
  if [ -e "$path" ]; then
    chown -R pptruser:pptruser "$path"
  fi
done

if [ -n "$INSPECT_WORKERS" ]; then
  set -- "$@" --node-args="--inspect=0.0.0.0:9229"
fi

exec runuser -u pptruser -- "$@"
