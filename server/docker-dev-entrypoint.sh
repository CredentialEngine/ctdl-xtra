#!/bin/sh
set -e

DEV_UID="${DEV_UID:-1000}"
DEV_GID="${DEV_GID:-1000}"

# Enable Node.js inspector when DEBUG matches this service (DEBUG_SERVICE=server|worker).
# DEBUG=1 (or true/yes/all) attaches all services; DEBUG=server,worker attaches listed ones only.
debug_inspect_enabled() {
  [ -n "${DEBUG:-}" ] || return 1
  [ -n "${DEBUG_SERVICE:-}" ] || return 1

  case "$DEBUG" in
    1|true|yes|all) return 0 ;;
  esac

  _old_ifs=$IFS
  IFS=','
  for _svc in $DEBUG; do
    _svc=$(echo "$_svc" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
    case "$_svc" in
      server|xtra)
        [ "$DEBUG_SERVICE" = "server" ] && { IFS=$_old_ifs; return 0; }
        ;;
      worker)
        [ "$DEBUG_SERVICE" = "worker" ] && { IFS=$_old_ifs; return 0; }
        ;;
    esac
  done
  IFS=$_old_ifs
  return 1
}

setup_node_inspect() {
  debug_inspect_enabled || return 0

  case "$DEBUG_SERVICE" in
    server) INSPECT_PORT="${SERVER_DBG_PORT:-9229}" ;;
    worker) INSPECT_PORT="${WORKER_DBG_PORT:-9230}" ;;
    *) return 0 ;;
  esac

  export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--inspect=0.0.0.0:${INSPECT_PORT}"
  echo "Node inspect enabled for ${DEBUG_SERVICE} on 0.0.0.0:${INSPECT_PORT}"
}

# worker.Dockerfile uses the default pptruser uid; align with xtra/DEV_UID for shared volumes.
usermod -o -u "$DEV_UID" pptruser
usermod -g "$DEV_GID" pptruser
chown -R pptruser: /home/pptruser

chown -R pptruser:pptruser /app
chown -R pptruser:pptruser /app/db 2>/dev/null || true

mkdir -p /data/extractions /app/dist /home/pptruser/.cache/puppeteer
chown -R pptruser: /data/extractions
chown -R pptruser: /home/pptruser/.cache

# xtra and worker share node_modules; serialize install/build to avoid races.
(
  flock -w 600 9 || exit 1
  runuser -u pptruser -- env CI=true pnpm install
  runuser -u pptruser -- pnpm run build
  chown -R pptruser:pptruser /app/node_modules /app/dist
) 9>/tmp/pnpm-install.lock

setup_node_inspect

if [ -n "${NODE_OPTIONS:-}" ]; then
  exec runuser -u pptruser -- env NODE_OPTIONS="$NODE_OPTIONS" "$@"
else
  exec runuser -u pptruser -- "$@"
fi
