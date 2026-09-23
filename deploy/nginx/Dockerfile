FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
HEALTHCHECK --interval=15s --timeout=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
