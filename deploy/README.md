# Deploy bootstrap (one-time)

## 1. age key
`age-keygen -o deploy/keys.txt` — public key goes in `deploy/.sops.yaml`; full file contents become the `SOPS_AGE_KEY` GitHub secret. Store the key in the team password manager. `keys.txt` is gitignored anywhere in the tree; never commit it.

## 2. Deploy SSH key
On a workstation: `ssh-keygen -t ed25519 -f deploy_key -C chatbotportal-deploy`.
- Private half (`deploy_key`) → GitHub secret `SSH_PRIVATE_KEY`.
- Public half (`deploy_key.pub`) → append to `~deploy/.ssh/authorized_keys` on the host.
- Host key pin: `ssh-keyscan chatbotportal.opdc.ai.in.th` → GitHub secret `SSH_KNOWN_HOSTS`.

## 3. GitHub Actions secrets (repo settings)
`SOPS_AGE_KEY`, `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`. The old `OPENROUTER_API_KEY` secret can be removed — it now lives in SOPS.

## 4. Host setup from scratch (new VPS, root only)

Do these steps once on a fresh Debian/Ubuntu VPS. Start as `root`. Replace
`PASTE_DEPLOY_KEY_PUB` with the contents of `deploy_key.pub` from step 2.

### 4.1 Update the system
```bash
apt-get update && apt-get upgrade -y
```

### 4.2 Install Docker Engine + Compose v2
The official script installs the engine, the Compose plugin, and buildx:
```bash
curl -fsSL https://get.docker.com | sh
docker version && docker compose version   # confirm both work
```

### 4.3 Create the `deploy` user
The CI runner connects as this user. It must be in the `docker` group. The
playbook uses `become: true`, so the user also needs passwordless `sudo`.
Note: `docker`-group membership is already root-equivalent (a container can
mount `/`), so adding `sudo` does not widen the blast radius.
```bash
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/deploy
chmod 440 /etc/sudoers.d/deploy
visudo -c   # verify sudoers syntax
```

### 4.4 Install the deploy SSH key
```bash
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo 'PASTE_DEPLOY_KEY_PUB' > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 4.5 Create the deploy directory
The playbook writes here (`deploy_dir` = `/opt/chatbotportal`):
```bash
install -d -m 755 -o deploy -g deploy /opt/chatbotportal
```

### 4.6 Open the firewall
Keep SSH (22) plus the web ports. Do not lock yourself out — allow 22 first.
```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable
```

### 4.7 Point DNS
Add an `A` record for `chatbotportal.opdc.ai.in.th` → the VPS public IP.
Caddy needs this resolvable to issue the TLS certificate.

### 4.8 Verify (as the deploy user)
```bash
su - deploy -c 'docker run --rm hello-world'   # docker works without sudo
sudo -n true && echo 'passwordless sudo OK'     # run as deploy
```
From your workstation, confirm key-based SSH works:
`ssh -i deploy_key deploy@chatbotportal.opdc.ai.in.th 'docker compose version'`.

## 5. Make GHCR packages public
After the first `release` run pushes them, in GitHub → Packages, set
`chatbotportal` and `chatbotportal-web` visibility to Public (the deploy host pulls anonymously).

## 6. Editing secrets later
From `deploy/`: `SOPS_AGE_KEY_FILE=keys.txt sops group_vars/all/secrets.sops.yaml`, edit, save — SOPS re-encrypts (recipients come from `deploy/.sops.yaml`). Commit the ciphertext.

## Rollback
Actions → release → Run workflow → enter an older tag (e.g. `v0.1.0`). Images are immutable per tag/SHA.
