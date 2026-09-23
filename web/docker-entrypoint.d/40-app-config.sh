#!/bin/sh

set -eu

target="/usr/share/nginx/html/config.js"

cat > "$target" <<EOF
window.__APP_CONFIG__ = {
  API_BASE_URL: '${API_BASE_URL:-}',
  OIDC_AUTHORITY: '${OIDC_AUTHORITY:-}',
  OIDC_CLIENT_ID: '${OIDC_CLIENT_ID:-}',
}
EOF
