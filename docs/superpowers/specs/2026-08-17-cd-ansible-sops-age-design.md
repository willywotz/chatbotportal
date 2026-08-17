# CD via GitHub Actions → Ansible + SOPS/age — Design

Date: 2026-08-17
Status: Approved for planning

## Problem

Today `release.yaml` runs on a **self-hosted runner on the app host**. It writes a
`.env` inline from a single GitHub Actions secret (`OPENROUTER_API_KEY`), hardcodes
the domain/ports/email in the workflow, then runs `docker compose up -d --build`.
Images build on the production host every deploy. Secrets are scattered (one in
GitHub, the DB password left at the insecure default `chatbot_secret`), and the
release logic lives in shell inside a YAML step.

Goal: a real continuous-deployment path — build once, deploy immutable images,
manage secrets as encrypted files in the repo — using **Ansible** (orchestration),
**SOPS** (secret encryption), and **age** (encryption backend).

## Decisions (locked)

| Question | Decision |
|---|---|
| Deploy trigger | GitHub Actions on tag push (`v*`) |
| Runner | GitHub-hosted `ubuntu-latest` (retire self-hosted runner) |
| Runner → host | SSH |
| age private key custody | GitHub Actions secret `SOPS_AGE_KEY` |
| Image build | Build in CI, push to GHCR; host pulls |
| GHCR visibility | Public (no pull auth on host) |
| Environments | Prod only (structure leaves room for staging) |
| age keys | One shared project keypair to start |

## Pipeline

```
git tag v0.2.0 && git push --tags
        │
        ▼
release.yaml  (ubuntu-latest)
  ├─ job build
  │    docker buildx backend + frontend
  │    push ghcr.io/willywotz/chatbotportal-{backend,frontend}
  │         tags: v0.2.0  +  <sha>   (public)
  └─ job deploy  (needs: build)
       ├─ install ansible + sops + age
       ├─ write age key   ← secrets.SOPS_AGE_KEY  → $SOPS_AGE_KEY_FILE
       ├─ setup SSH       ← secrets.SSH_PRIVATE_KEY / SSH_KNOWN_HOSTS
       └─ ansible-playbook deploy/deploy.yml -i deploy/inventory/prod.yml
                              -e image_tag=v0.2.0
                │  (SSH → chatbotportal.opdc.ai.in.th)
                ▼
          host: template .env (0600) → docker compose pull → up -d
```

`ci.yaml` is unchanged (tests on PR / push to main). Deploy is tag-scoped and
independent of CI.

## Repository layout

```
deploy/
  ansible.cfg
  inventory/
    prod.yml                  # the one prod host
  group_vars/
    all.yml                   # NON-secret config (cleartext, committed)
    all/secrets.sops.yaml     # SOPS+age encrypted secrets (ciphertext, committed)
  deploy.yml                  # the playbook
  templates/
    env.j2                    # renders host .env from vars + decrypted secrets
.sops.yaml                    # creation rule → age recipient(s)
```

The `community.sops` Ansible collection provides a vars plugin that
**auto-decrypts** `group_vars/all/secrets.sops.yaml` as ordinary group vars when
`SOPS_AGE_KEY`/`SOPS_AGE_KEY_FILE` is present. No explicit decrypt step; plaintext
secrets never land on disk.

## Secret vs config split

**SOPS-encrypted** (`deploy/group_vars/all/secrets.sops.yaml`, committed ciphertext):
- `openrouter_api_key`
- `postgres_password`  — replaces the insecure `chatbot_secret` default

**Plain config** (`deploy/group_vars/all.yml`, committed cleartext, non-secret):
- `cert_domain: chatbotportal.opdc.ai.in.th`
- `cert_email: dogajack@gmail.com`
- `external_http_port: 80`, `external_https_port: 443`, `external_postgres_port: 5432`
- `cors_origins` (derived from `cert_domain`)
- `env: production`
- `image_repo: ghcr.io/willywotz/chatbotportal`
- `deploy_dir: /opt/chatbotportal`

**GitHub Actions secrets** (3 total):
- `SOPS_AGE_KEY` — age private key (decrypts SOPS files in CI)
- `SSH_PRIVATE_KEY` — deploy key for the host
- `SSH_KNOWN_HOSTS` — host key pin (no `StrictHostKeyChecking=no`)

The old inline `OPENROUTER_API_KEY` GitHub secret is retired — SOPS is the single
source of truth for runtime secrets.

## Compose change

Add `image:` to the two build services in the base `compose.yaml`; keep `build:` for
local use only:

```yaml
backend:
  image: ghcr.io/willywotz/chatbotportal-backend:${IMAGE_TAG:-latest}
  build: { context: ./backend, target: production }

frontend:
  image: ghcr.io/willywotz/chatbotportal-frontend:${IMAGE_TAG:-latest}
  build: { context: ./frontend, target: production }
```

On the host, `docker compose pull` fetches the image and `up -d` (no `--build`) uses
it — the build context is never read, so the absent source tree is fine. Local dev is
untouched: `compose.override.yaml` still drives `build`/`watch`. `POSTGRES_PASSWORD`
in `compose.yaml` keeps its `${...}` reference; the value now comes from the templated
`.env`, not the hardcoded default.

## Deploy playbook (`deploy/deploy.yml`, host tasks)

Runs against `inventory/prod.yml` over SSH. Tasks:

1. `file`: ensure `{{ deploy_dir }}` exists.
2. `template`: `env.j2` → `{{ deploy_dir }}/.env`, mode `0600`. Renders `IMAGE_TAG`,
   the plain config vars, and the decrypted secrets.
3. `copy`: repo `compose.yaml` → `{{ deploy_dir }}/compose.yaml`.
4. `community.docker.docker_compose_v2`: `project_src={{ deploy_dir }}`,
   `pull: always`, `remove_orphans: true`, `state: present` (= `pull` then `up -d`).
5. `command`: `docker image prune -f` (drop dangling images).

`image_tag` is passed via `-e image_tag=<tag>` from the workflow; `env.j2` writes it
as `IMAGE_TAG` so compose resolves the `image:` refs.

## `.sops.yaml`

```yaml
creation_rules:
  - path_regex: deploy/group_vars/.*/secrets\.sops\.ya?ml$
    age: age1<project-public-key>
```

Editing secrets: an operator with the age private key runs
`sops deploy/group_vars/all/secrets.sops.yaml`, edits in cleartext, saves — SOPS
re-encrypts. CI decrypts with the same key from `SOPS_AGE_KEY`.

## Rollback

Re-run `release.yaml` via `workflow_dispatch` pinned to an older tag. Images are
immutable by tag/SHA, so redeploying an old tag is a clean, deterministic revert. No
DB rollback is in scope.

## Assumptions & non-goals

- **Docker + compose already installed on the host.** The playbook deploys the app;
  it does not provision the box. A bootstrap role (install docker, create user, open
  firewall) is a later addition if wanted.
- **Single prod host / no staging.** A second environment = add `inventory/staging.yml`
  + `group_vars` + a trigger; the layout already supports it.
- **One shared project age keypair.** Upgrade path: add per-operator + CI age
  recipients in `.sops.yaml` and `sops updatekeys` to re-encrypt.
- **No blue/green or zero-downtime.** `docker compose up -d` recreates changed
  services in place; brief restart is acceptable. Caddy fronts TLS as today.
- **DB migrations** run as they do now (backend on startup / existing mechanism); not
  changed by this design.

## Follow-up: host & key bootstrap (one-time, out of CD)

Before the first automated deploy: generate the age keypair, put the public key in
`.sops.yaml`, encrypt `secrets.sops.yaml`, load `SOPS_AGE_KEY` / `SSH_PRIVATE_KEY` /
`SSH_KNOWN_HOSTS` into GitHub, and install the deploy key's public half on the host.
These steps are documented in the implementation plan, not automated by the pipeline.
