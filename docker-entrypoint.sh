#!/bin/sh
# Refuse to boot an unconfigured production image rather than half-working.
set -eu

if [ "${APP_ENV:-production}" = "production" ] && [ -z "${SECRET_KEY:-}" ]; then
  echo "fatal: SECRET_KEY must be set when APP_ENV=production" >&2
  exit 1
fi

_STATE="${DATA_DIR:-/var/lib/message_pusher}"
mkdir -p "$_STATE/instance" "$_STATE/log"

exec "$@"
