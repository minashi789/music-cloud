#!/bin/sh
set -eu

AUTH_USER="$(cat /run/secrets/tagr_login)"
AUTH_PASSWORD="$(cat /run/secrets/tagr_password)"
AUTH_SECRET="$(cat /run/secrets/tagr_secret)"
export AUTH_USER AUTH_PASSWORD AUTH_SECRET

exec /app/docker-entrypoint.sh
