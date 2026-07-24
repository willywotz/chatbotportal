#!/bin/sh
# Turns the TLS server block on once a Let's Encrypt cert for $CERT_DOMAIN exists.
#
# Mounted into the nginx image's /docker-entrypoint.d/, so it runs before nginx
# starts. It then keeps watching in the background: a first issuance or a certbot
# renewal is picked up and reloaded without restarting the container.
set -e

TLS_CONF=/etc/nginx/conf.d/tls.conf
REDIRECT_CONF=/etc/nginx/redirect/redirect.conf
LIVE_CERT="/etc/letsencrypt/live/${CERT_DOMAIN}/fullchain.pem"

cert_mtime() {
    [ -n "${CERT_DOMAIN}" ] && stat -c %Y "$LIVE_CERT" 2>/dev/null || echo none
}

apply() {
    mkdir -p "$(dirname "$REDIRECT_CONF")"
    if [ "$(cert_mtime)" = none ]; then
        rm -f "$TLS_CONF" "$REDIRECT_CONF"
        echo "[tls] no cert for '${CERT_DOMAIN:-<unset>}' — serving plain HTTP"
        return
    fi
    sed "s|__DOMAIN__|${CERT_DOMAIN}|g" /etc/nginx/tls.conf.template > "$TLS_CONF"
    # Server-level `if` is safe for a bare return; a server-level `return` would
    # also swallow the ACME location, which must stay on plain HTTP.
    # echo 'if ($request_uri !~ "^/\.well-known/acme-challenge/") { return 301 https://$host$request_uri; }' > "$REDIRECT_CONF"
    cat <<'EOF' > "$REDIRECT_CONF"
# Default redirect flag to false ("00")
set $should_redirect "00";

# Check 1: Request is not an ACME challenge -> append '1'
if ($request_uri !~ "^/\.well-known/acme-challenge/") {
    set $should_redirect "1";
}

# Check 2: $host does not look like an IP address -> append '1'
# Matches standard IPv4 addresses (e.g. 192.168.1.1)
if ($host !~ "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$") {
    set $should_redirect "${should_redirect}1";
}

# Perform 301 redirect only if both conditions are met ("11")
if ($should_redirect = "11") {
    return 301 https://$host$request_uri;
}
EOF
    echo "[tls] serving HTTPS for ${CERT_DOMAIN}"
}

apply
last=$(cert_mtime)

while :; do
    sleep 3600
    current=$(cert_mtime)
    [ "$current" = "$last" ] && continue
    last=$current
    apply
    nginx -s reload
done &
