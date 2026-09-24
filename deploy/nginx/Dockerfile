FROM nginx
COPY default.conf.template /etc/nginx/templates/

HEALTHCHECK --interval=15s --timeout=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
