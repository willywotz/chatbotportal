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
