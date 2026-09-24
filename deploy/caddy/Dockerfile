FROM caddy:2

RUN apk add --no-cache nss-tools

COPY Caddyfile /etc/caddy/Caddyfile

HEALTHCHECK --interval=15s --timeout=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
