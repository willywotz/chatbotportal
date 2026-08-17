# HTTPS / Let's Encrypt (Caddy automatic HTTPS)

The gateway (`caddy` service) terminates TLS for one public hostname, with
certificates issued and renewed **automatically** by Caddy — no `certbot`
container, no `certonly` run, no renewal loop. Production host:
`chatbotportal.opdc.ai.in.th`.

## How it fits together

| Piece | Role |
|---|---|
| `caddy/Caddyfile` | The single config: site address, TLS, routing contract, timeouts. |
| `caddy` service | Obtains + renews the Let's Encrypt cert itself (HTTP-01 / TLS-ALPN). |
| `caddy_data` volume | Persists the ACME account + certs across restarts (`/data`). |
| `caddy_config` volume | Caddy's runtime config cache (`/config`). |

`SITE_ADDRESS` (sourced from `CERT_DOMAIN`) drives the listen mode:

- **Empty** — Caddy listens on `:80` plain HTTP. No cert is requested. This is
  local dev: nothing to configure, nothing fails.
- **A hostname** (`chatbotportal.opdc.ai.in.th`) — Caddy listens on `:80` and
  `:443`, requests a cert for that hostname on first start, serves HTTPS on
  `:443`, and `301`-redirects `:80` to `:443`. Renewals are automatic; Caddy
  reloads the renewed cert itself.

## Prerequisites

- `chatbotportal.opdc.ai.in.th` resolves to the host running compose.
- Port **80** is open to the public internet and published by the `caddy`
  service (`EXTERNAL_HTTP_PORT=80`). Caddy completes the HTTP-01 challenge on
  port 80; it cannot use another port.
- Port **443** published (`EXTERNAL_HTTPS_PORT=443`).
- `CERT_EMAIL` set (a Let's Encrypt account contact for expiry notices).

## First issuance

There is no manual issuance step. On the prod host, with `CERT_DOMAIN` and
`CERT_EMAIL` set in `.env`:

```bash
docker compose up -d caddy
docker compose logs caddy | grep -i 'certificate\|obtain'
```

Caddy obtains the cert on first start and serves HTTPS within seconds. The
first request to `https://chatbotportal.opdc.ai.in.th/` should succeed.

## Renewal

Unattended. Caddy renews certificates at ~30 days remaining and reloads them
itself — no deploy, no restart, no `certbot` job. Check the cert:

```bash
echo | openssl s_client -connect chatbotportal.opdc.ai.in.th:443 2>/dev/null \
  | openssl x509 -noout -dates
docker compose logs caddy | grep -i 'renew'
```

## Turning TLS off

Unset `CERT_DOMAIN` and restart caddy. Caddy goes back to plain HTTP on `:80`;
the cert stays in the `caddy_data` volume.
