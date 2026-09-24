# k3s single-VPS deploy

Alternative to `compose.yaml` for a one-node k3s host.

## Edge chain

```
Cloudflare (TLS)
  -> Traefik            k3s built-in ingress controller, host 80/443
    -> Ingress gateway  catch-all "/" for the host
      -> gateway nginx  path routing (/api, /jaeger, /, timeouts, CF headers)
        -> backend / web / jaeger
```

TLS ends at Cloudflare. Every hop below it is plain HTTP.

## Files

| File | Holds |
|---|---|
| `namespace.yaml` | Namespace `chatbotportal` |
| `config.yaml` | Secret + ConfigMap (shared app config) |
| `postgres.yaml` | PVC (`local-path` 10Gi) + Deployment + Service |
| `jaeger.yaml` | Deployment + Service |
| `backend.yaml` | Deployment + Service |
| `web.yaml` | Deployment + Service |
| `gateway.yaml` | nginx ConfigMap + Deployment + Service + Ingress |
| `kustomization.yaml` | Apply order for all of the above |

## Before you apply

1. Replace every `REPLACE_WITH_*` value in `config.yaml`.
2. Set the two image tags (`backend.yaml`, `web.yaml`) to the release tag you deploy (e.g. `v0.1.0`).
3. Set the host in `config.yaml` (`CORS_ORIGINS` / `OIDC_*` / `API_BASE_URL`) AND the Ingress host in `gateway.yaml` to your domain.
4. Make the GHCR packages public for anonymous pull (see `../README.md`).

## Apply

```bash
kubectl apply -k deploy/k3s
kubectl -n chatbotportal get pods,svc,ingress
```

Plain `kubectl apply -f deploy/k3s/` also works but does not guarantee
apply order; prefer `-k` so the Namespace and config land first.
