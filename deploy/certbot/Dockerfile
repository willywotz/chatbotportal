FROM alpine
WORKDIR /etc/letsencrypt

RUN apk add --no-cache ca-certificates openssl

CMD openssl req -x509 -newkey rsa:2048 -nodes -sha256 \
  -days 365 \
  -keyout /etc/letsencrypt/localhost-key.pem \
  -out /etc/letsencrypt/localhost.pem \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
