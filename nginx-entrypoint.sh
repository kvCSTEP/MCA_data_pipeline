#!/bin/sh
set -e

if [ -z "$1" ]; then
  echo "ERROR: No auth token argument provided to entrypoint" >&2
  exit 1
fi

export WORKER_TOKEN_B64=$(printf '%s' "$1" | base64)

envsubst '${WORKER_TOKEN_B64}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf

echo "Rendered auth mode line:"
grep -A3 api_auth_mode /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'