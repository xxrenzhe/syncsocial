#!/usr/bin/env bash
set -euo pipefail

if [ -f /etc/nginx/nginx.conf ]; then
  nginx -t -c /etc/nginx/nginx.conf
fi

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

