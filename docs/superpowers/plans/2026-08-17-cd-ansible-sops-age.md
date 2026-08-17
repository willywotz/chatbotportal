# CD via Ansible + SOPS/age Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the self-hosted `docker compose up --build` release with a CD pipeline that builds images in CI, pushes them to GHCR, and deploys via Ansible using SOPS/age-encrypted secrets.

**Architecture:** On a `v*` tag, a GitHub-hosted `ubuntu-latest` runner builds and pushes the two images to public GHCR, then runs `ansible-playbook` over SSH to the prod host. Ansible renders a `0600` `.env` from cleartext group vars plus SOPS-decrypted secrets, copies `compose.yaml`, and runs `docker compose pull && up -d`. The age private key, SSH key, and host key pin live in GitHub Actions secrets.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, ansible-core, `community.sops`, `community.docker`, SOPS, age, Docker Compose v2.

**Spec:** `docs/superpowers/specs/2026-08-17-cd-ansible-sops-age-design.md`

## Global Constraints

- Images: backend = `ghcr.io/willywotz/chatbotportal`, frontend = `ghcr.io/willywotz/chatbotportal-web`. Public. Tags: `<git-tag>` and `<git-sha>`.
- Host deploy dir: `/opt/chatbotportal`. `.env` mode `0600`.
- Prod domain: `chatbotportal.opdc.ai.in.th`. Cert email: `dogajack@gmail.com`.
- Dockerfile build targets: both `backend/Dockerfile` and `frontend/Dockerfile` use target `production`.
- Secrets in SOPS only: `openrouter_api_key`, `postgres_password`. All other config is cleartext group vars.
- GitHub Actions secrets required: `SOPS_AGE_KEY`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`.
- Full English endpoint/route names, 15-Factor + Clean Architecture per repo CLAUDE.md. No secret plaintext (age private key, real API key, DB password) is ever committed — only SOPS ciphertext is committed.
- Repo convention: GitHub Actions `uses:` are SHA-pinned. The `uses:` below show version tags for readability — pin each to its commit SHA (same style as `.github/workflows/ci.yaml`) when writing the file.

---

### Task 1: Compose image references

Make `compose.yaml` pull pre-built GHCR images while keeping `build:` for local use only.

**Files:**
- Modify: `compose.yaml` (backend + frontend services)

**Interfaces:**
- Produces: `backend` and `frontend` services resolve `image:` from `${IMAGE_TAG:-latest}`. The host `.env` (Task 4) supplies `IMAGE_TAG`.

- [ ] **Step 1: Add `image:` to backend service**

In `compose.yaml`, the `backend:` service — add an `image:` key above `build:`:

```yaml
  backend:
    image: ghcr.io/willywotz/chatbotportal:${IMAGE_TAG:-latest}
    build:
      context: ./backend
      target: production
```

- [ ] **Step 2: Add `image:` to frontend service**

```yaml
  frontend:
    image: ghcr.io/willywotz/chatbotportal-web:${IMAGE_TAG:-latest}
    build:
      context: ./frontend
      target: production
```

- [ ] **Step 3: Verify compose still parses and resolves the tag**

Run: `IMAGE_TAG=v0.1.0 docker compose -f compose.yaml config | grep -E 'image: ghcr'`
Expected: two lines — `image: ghcr.io/willywotz/chatbotportal:v0.1.0` and `image: ghcr.io/willywotz/chatbotportal-web:v0.1.0`.

- [ ] **Step 4: Verify local dev override still builds**

Run: `docker compose config --quiet`
Expected: exit 0 (base + `compose.override.yaml` merge is still valid; dev builds from source as before).

- [ ] **Step 5: Commit**

```bash
git add compose.yaml
git commit -m "feat(deploy): reference GHCR images in compose for CD pulls"
```

---

### Task 2: Ansible skeleton, inventory, and non-secret vars

Create the `deploy/` Ansible project with everything except the encrypted secrets and the playbook.

**Files:**
- Create: `deploy/ansible.cfg`
- Create: `deploy/requirements.yml`
- Create: `deploy/inventory/prod.yml`
- Create: `deploy/group_vars/all.yml`
- Modify: `.gitignore` (ignore installed collections + age keys)

**Interfaces:**
- Produces: inventory host `chatbotportal`; group vars `env`, `cert_domain`, `cert_email`, `external_http_port`, `external_https_port`, `external_postgres_port`, `cors_origins`, `postgres_db`, `postgres_user`, `deploy_dir`. Task 4's template and playbook consume these.

- [ ] **Step 1: Write `deploy/ansible.cfg`**

```ini
[defaults]
inventory = inventory/prod.yml
collections_path = ./.ansible/collections
host_key_checking = True
retry_files_enabled = False
stdout_callback = yaml
# community.sops.sops vars plugin auto-decrypts *.sops.yaml in group_vars/host_vars
vars_plugins_enabled = host_group_vars,community.sops.sops
```

- [ ] **Step 2: Write `deploy/requirements.yml`**

```yaml
collections:
  - name: community.sops
  - name: community.docker
```

- [ ] **Step 3: Write `deploy/inventory/prod.yml`**

`ansible_user` must be a host account that is a member of the `docker` group (see bootstrap in Task 6).

```yaml
all:
  hosts:
    chatbotportal:
      ansible_host: chatbotportal.opdc.ai.in.th
      ansible_user: deploy
      ansible_python_interpreter: /usr/bin/python3
```

- [ ] **Step 4: Write `deploy/group_vars/all.yml`**

Image names are NOT here — they live in `compose.yaml` (Task 1) and `release.yaml` (Task 5); duplicating them in vars would drift.

```yaml
env: production
cert_domain: chatbotportal.opdc.ai.in.th
cert_email: dogajack@gmail.com
external_http_port: 80
external_https_port: 443
external_postgres_port: 5432
cors_origins: '["https://{{ cert_domain }}"]'
postgres_db: chatbot
postgres_user: chatbot
deploy_dir: /opt/chatbotportal
```

- [ ] **Step 5: Extend `.gitignore`**

Add these lines to `.gitignore`:

```
# Ansible installed collections + local age keys
deploy/.ansible/
keys.txt
```

- [ ] **Step 6: Install collections and verify inventory**

Run:
```bash
cd deploy && ansible-galaxy collection install -r requirements.yml && ansible-inventory --list
```
Expected: collections install without error; JSON output lists host `chatbotportal` with `ansible_host: chatbotportal.opdc.ai.in.th`.

- [ ] **Step 7: Commit**

```bash
git add deploy/ansible.cfg deploy/requirements.yml deploy/inventory/prod.yml deploy/group_vars/all.yml .gitignore
git commit -m "feat(deploy): ansible skeleton, inventory, and non-secret group vars"
```

---

### Task 3: SOPS + age encrypted secrets

Generate the project age key, wire `.sops.yaml`, and commit the encrypted secrets file (ciphertext only).

> The age **private** key and the real secret **values** are operator inputs — never write them into this repo or the plan. Only the encrypted `secrets.sops.yaml` (ciphertext) is committed.

**Files:**
- Create: `.sops.yaml`
- Create: `deploy/group_vars/all/secrets.sops.yaml` (committed as ciphertext)

**Interfaces:**
- Produces: decrypted vars `openrouter_api_key`, `postgres_password`, auto-loaded by the `community.sops.sops` vars plugin whenever `SOPS_AGE_KEY_FILE`/`SOPS_AGE_KEY` is set. Task 4's template consumes them.

- [ ] **Step 1: Generate the project age keypair (operator, local, not committed)**

Run:
```bash
age-keygen -o keys.txt
grep 'public key' keys.txt
```
Expected: prints `# public key: age1...`. Keep `keys.txt` out of git (already gitignored). Store its contents — this is the value for the `SOPS_AGE_KEY` GitHub secret (Task 6).

- [ ] **Step 2: Write `.sops.yaml` with the public key**

Replace `age1PUBLICKEY` with the public key from Step 1:

```yaml
creation_rules:
  - path_regex: deploy/group_vars/.*/secrets\.sops\.ya?ml$
    age: age1PUBLICKEY
```

- [ ] **Step 3: Create and encrypt the secrets file**

Use a strong generated DB password and the real OpenRouter key. `sops` encrypts in place using `.sops.yaml`:

```bash
mkdir -p deploy/group_vars/all
cat > deploy/group_vars/all/secrets.sops.yaml <<'YAML'
postgres_password: REPLACE_WITH_STRONG_PASSWORD
openrouter_api_key: REPLACE_WITH_REAL_KEY
YAML
SOPS_AGE_KEY_FILE=keys.txt sops --encrypt --in-place deploy/group_vars/all/secrets.sops.yaml
```

- [ ] **Step 4: Verify the file is ciphertext, and decrypt round-trips**

Run:
```bash
grep -q 'ENC\[' deploy/group_vars/all/secrets.sops.yaml && echo CIPHERTEXT_OK
SOPS_AGE_KEY_FILE=keys.txt sops --decrypt deploy/group_vars/all/secrets.sops.yaml
```
Expected: prints `CIPHERTEXT_OK`; decrypt shows the two cleartext keys `postgres_password` and `openrouter_api_key`. Confirm no cleartext secret remains in the on-disk file (only `sops:` metadata + `ENC[...]` values).

- [ ] **Step 5: Commit (ciphertext only)**

```bash
git add .sops.yaml deploy/group_vars/all/secrets.sops.yaml
git commit -m "feat(deploy): SOPS/age encrypted runtime secrets"
```

---

### Task 4: Deploy playbook + `.env` template

The playbook that renders `.env`, copies compose, and runs the pull/up on the host.

**Files:**
- Create: `deploy/templates/env.j2`
- Create: `deploy/deploy.yml`

**Interfaces:**
- Consumes: group vars from Task 2, decrypted secrets from Task 3, and `image_tag` passed via `-e image_tag=<tag>` (Task 5).
- Produces: `{{ deploy_dir }}/.env` (mode `0600`) and `{{ deploy_dir }}/compose.yaml` on the host; the running stack.

- [ ] **Step 1: Write `deploy/templates/env.j2`**

Every value the base `compose.yaml` reads. `IMAGE_TAG` comes from the `image_tag` play var.

```jinja
ENV={{ env }}
IMAGE_TAG={{ image_tag }}
EXTERNAL_HTTP_PORT={{ external_http_port }}
EXTERNAL_HTTPS_PORT={{ external_https_port }}
EXTERNAL_POSTGRES_PORT={{ external_postgres_port }}
CERT_DOMAIN={{ cert_domain }}
CERT_EMAIL={{ cert_email }}
CORS_ORIGINS={{ cors_origins }}
POSTGRES_DB={{ postgres_db }}
POSTGRES_USER={{ postgres_user }}
POSTGRES_PASSWORD={{ postgres_password }}
OPENROUTER_API_KEY={{ openrouter_api_key }}
```

- [ ] **Step 2: Write `deploy/deploy.yml`**

```yaml
- name: Deploy chatbotportal
  hosts: all
  become: true
  gather_facts: false
  tasks:
    - name: Ensure deploy directory exists
      ansible.builtin.file:
        path: "{{ deploy_dir }}"
        state: directory
        mode: "0755"

    - name: Render environment file
      ansible.builtin.template:
        src: templates/env.j2
        dest: "{{ deploy_dir }}/.env"
        mode: "0600"

    - name: Copy compose file
      ansible.builtin.copy:
        src: "{{ playbook_dir }}/../compose.yaml"
        dest: "{{ deploy_dir }}/compose.yaml"
        mode: "0644"

    - name: Pull images and start the stack
      community.docker.docker_compose_v2:
        project_src: "{{ deploy_dir }}"
        pull: always
        remove_orphans: true
        state: present

    - name: Prune dangling images
      ansible.builtin.command: docker image prune -f
      changed_when: false
```

- [ ] **Step 3: Verify playbook syntax**

Run: `cd deploy && ansible-playbook deploy.yml --syntax-check -e image_tag=v0.1.0`
Expected: exit 0, no syntax errors (host connection is not attempted by `--syntax-check`).

- [ ] **Step 4: Verify template renders with real vars (offline)**

Renders `env.j2` against the group vars + decrypted secrets, no host needed:

```bash
cd deploy && SOPS_AGE_KEY_FILE=../keys.txt ansible -i inventory/prod.yml chatbotportal \
  -m ansible.builtin.template -a "src=templates/env.j2 dest=/tmp/env.rendered mode=0600" \
  --connection=local -e image_tag=v0.1.0
grep -E '^IMAGE_TAG=v0.1.0$|^POSTGRES_PASSWORD=.+|^OPENROUTER_API_KEY=.+' /tmp/env.rendered
rm -f /tmp/env.rendered
```
Expected: `IMAGE_TAG=v0.1.0`, and non-empty `POSTGRES_PASSWORD` / `OPENROUTER_API_KEY` lines — proving the SOPS vars plugin decrypted and the template filled. (This writes to local `/tmp` via `--connection=local`; it does not touch the prod host.)

- [ ] **Step 5: Commit**

```bash
git add deploy/templates/env.j2 deploy/deploy.yml
git commit -m "feat(deploy): playbook renders .env and runs compose pull/up"
```

---

### Task 5: Release workflow (build → push → deploy)

Replace the old self-hosted release with the two-job CD workflow.

**Files:**
- Modify (replace contents): `.github/workflows/release.yaml`

**Interfaces:**
- Consumes: GitHub secrets `SOPS_AGE_KEY`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS` (Task 6); `deploy/` project from Tasks 2–4.
- Produces: pushed GHCR images tagged `<ref_name>` + `<sha>`; a deployed stack.

- [ ] **Step 1: Replace `.github/workflows/release.yaml`**

SHA-pin each `uses:` before saving (repo convention — see Global Constraints).

```yaml
name: release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      tag:
        description: "Existing image tag to redeploy (e.g. v0.1.0)"
        required: true

permissions:
  contents: read
  packages: write

jobs:
  build:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push backend
        uses: docker/build-push-action@v6
        with:
          context: ./backend
          target: production
          push: true
          tags: |
            ghcr.io/willywotz/chatbotportal:${{ github.ref_name }}
            ghcr.io/willywotz/chatbotportal:${{ github.sha }}
      - name: Build and push frontend
        uses: docker/build-push-action@v6
        with:
          context: ./frontend
          target: production
          push: true
          tags: |
            ghcr.io/willywotz/chatbotportal-web:${{ github.ref_name }}
            ghcr.io/willywotz/chatbotportal-web:${{ github.sha }}

  deploy:
    needs: build
    if: always() && (needs.build.result == 'success' || github.event_name == 'workflow_dispatch')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install ansible, sops, age
        run: |
          pipx install ansible-core
          sudo apt-get update
          sudo apt-get install -y age
          SOPS_VERSION=v3.9.4
          curl -sSL "https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.amd64" -o /usr/local/bin/sops
          sudo chmod +x /usr/local/bin/sops
      - name: Install Ansible collections
        run: ansible-galaxy collection install -r deploy/requirements.yml
      - name: Load age key
        run: |
          mkdir -p ~/.config/sops/age
          printf '%s\n' "${{ secrets.SOPS_AGE_KEY }}" > ~/.config/sops/age/keys.txt
          chmod 600 ~/.config/sops/age/keys.txt
      - name: Configure SSH
        run: |
          mkdir -p ~/.ssh
          printf '%s\n' "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          printf '%s\n' "${{ secrets.SSH_KNOWN_HOSTS }}" > ~/.ssh/known_hosts
      - name: Deploy with Ansible
        working-directory: deploy
        env:
          SOPS_AGE_KEY_FILE: /home/runner/.config/sops/age/keys.txt
        run: ansible-playbook deploy.yml -e image_tag=${{ github.event.inputs.tag || github.ref_name }}
```

- [ ] **Step 2: Lint the workflow**

Run: `actionlint .github/workflows/release.yaml` (if `actionlint` unavailable, fall back to `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yaml'))" && echo YAML_OK`).
Expected: no errors / `YAML_OK`.

- [ ] **Step 3: Confirm the old self-hosted logic is gone**

Run: `grep -nE 'self-hosted|--build|OPENROUTER_API_KEY' .github/workflows/release.yaml || echo CLEAN`
Expected: `CLEAN` — no self-hosted runner, no on-host `--build`, no inline OpenRouter secret.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yaml
git commit -m "feat(deploy): CD release workflow builds to GHCR and deploys via Ansible"
```

---

### Task 6: Bootstrap runbook + CONTEXT.md

Document the one-time operator steps (keys, GitHub secrets, host prep, GHCR publicness) and record the change.

**Files:**
- Create: `docs/deploy-bootstrap.md`
- Modify: `CONTEXT.md`

**Interfaces:**
- Consumes: outputs from Tasks 3 & 5 (age key, image names, required secrets). No code depends on this task; it is the human runbook.

- [ ] **Step 1: Write `docs/deploy-bootstrap.md`**

```markdown
# Deploy bootstrap (one-time)

## 1. age key
`age-keygen -o keys.txt` — public key goes in `.sops.yaml`; full file contents become the `SOPS_AGE_KEY` GitHub secret. Store `keys.txt` in the team password manager; never commit it.

## 2. Deploy SSH key
On a workstation: `ssh-keygen -t ed25519 -f deploy_key -C chatbotportal-deploy`.
- Private half (`deploy_key`) → GitHub secret `SSH_PRIVATE_KEY`.
- Public half (`deploy_key.pub`) → append to `~deploy/.ssh/authorized_keys` on the host.
- Host key pin: `ssh-keyscan chatbotportal.opdc.ai.in.th` → GitHub secret `SSH_KNOWN_HOSTS`.

## 3. GitHub Actions secrets (repo settings)
`SOPS_AGE_KEY`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`. The old `OPENROUTER_API_KEY` secret can be removed — it now lives in SOPS.

## 4. Host prep
- A `deploy` user in the `docker` group: `usermod -aG docker deploy`.
- Docker Engine + Compose v2 installed.
- Ports 80/443 open. DNS points `chatbotportal.opdc.ai.in.th` at the host.

## 5. Make GHCR packages public
After the first `release` run pushes them, in GitHub → Packages, set
`chatbotportal` and `chatbotportal-web` visibility to Public (the deploy host pulls anonymously).

## 6. Editing secrets later
`SOPS_AGE_KEY_FILE=keys.txt sops deploy/group_vars/all/secrets.sops.yaml`, edit, save — SOPS re-encrypts. Commit the ciphertext.

## Rollback
Actions → release → Run workflow → enter an older tag (e.g. `v0.1.0`). Images are immutable per tag/SHA.
```

- [ ] **Step 2: Update `CONTEXT.md`**

Add a short entry under the current date summarizing: release is now CD via GitHub Actions → GHCR → Ansible/SOPS/age; secrets in `deploy/group_vars/all/secrets.sops.yaml`; bootstrap in `docs/deploy-bootstrap.md`.

- [ ] **Step 3: Verify links resolve**

Run: `test -f docs/deploy-bootstrap.md && grep -q deploy-bootstrap CONTEXT.md && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add docs/deploy-bootstrap.md CONTEXT.md
git commit -m "docs(deploy): CD bootstrap runbook and context update"
```

---

## Self-Review

**Spec coverage:**
- Pipeline (build→push→deploy) → Task 5. ✅
- Repo layout (`deploy/` tree, `.sops.yaml`) → Tasks 2, 3, 4. ✅
- Secret/config split → Task 2 (config), Task 3 (secrets). ✅
- 3 GitHub secrets, retire old inline secret → Tasks 5 & 6. ✅
- Compose `image:` change → Task 1. ✅
- Playbook host tasks (template/copy/pull-up/prune) → Task 4. ✅
- Rollback via `workflow_dispatch` older tag → Task 5 input + Task 6 runbook. ✅
- Bootstrap (age key, GH secrets, deploy key, GHCR publicness) → Task 6. ✅

**Placeholder scan:** The only `REPLACE_WITH_*` / `age1PUBLICKEY` tokens are deliberate operator inputs (real secret values, real key) that MUST NOT be committed in cleartext — flagged as such, not plan gaps.

**Type/name consistency:** Image names, `deploy_dir`, var names (`image_tag`, `postgres_password`, `openrouter_api_key`, `cors_origins`) are identical across compose, group vars, template, playbook, and workflow. `SOPS_AGE_KEY_FILE` path in the workflow (`/home/runner/.config/sops/age/keys.txt`) matches the file written in the "Load age key" step.
