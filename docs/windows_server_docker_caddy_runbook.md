# Windows Server + Docker + Caddy Runbook (Production)

This runbook deploys MDR App on Windows Server using Linux containers under WSL2.

## Target Architecture

- Host OS: Windows Server 2022+ (recommended)
- Runtime: WSL2 + Ubuntu 22.04 + Docker Engine
- Reverse proxy + TLS: Caddy container
- Database: PostgreSQL container
- Public ports: `80`, `443`
- Private/local-only ports: `8000`, `5432`
- Deploy model: Git tag pull on server (`git fetch --tags` + `git checkout --detach vX.Y.Z`)
- Frontend build model: Docker multi-stage (no need to commit `static/dist`)

## 1) Desktop Release Steps

Run from your workstation:

```powershell
git checkout main
git pull --ff-only
npm ci
npm run typecheck
```

Create and push release tag:

```powershell
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

Notes:

- `npm run build` is not required for deployment.
- `static/dist` is built inside Docker image on server.

## 2) One-Time Windows Server Preparation

Open elevated PowerShell:

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

Reboot server, then:

```powershell
wsl -d Ubuntu-22.04
```

Inside Ubuntu:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release git openssh-client
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Exit Ubuntu and open it again.

Enable systemd in WSL:

```bash
sudo tee /etc/wsl.conf > /dev/null << 'EOF'
[boot]
systemd=true
EOF
exit
```

From PowerShell:

```powershell
wsl --shutdown
wsl -d Ubuntu-22.04
```

Back in Ubuntu:

```bash
sudo systemctl enable docker
sudo systemctl start docker
docker --version
docker compose version
git --version
```

## 3) One-Time Git Access Setup (WSL -> origin)

Generate deploy key:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/mdr_deploy -C "mdr-prod-wsl"
cat ~/.ssh/mdr_deploy.pub
```

Add the printed public key to your Git provider as a read-only deploy key.

Configure SSH:

```bash
cat > ~/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/mdr_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh-keyscan github.com >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts
ssh -T git@github.com
```

## 4) Initial Deploy on Server

Inside Ubuntu:

```bash
sudo mkdir -p /opt/mdr_app
sudo chown -R $USER:$USER /opt/mdr_app
git clone git@github.com:<ORG>/<REPO>.git /opt/mdr_app
cd /opt/mdr_app
git fetch origin --tags --prune
git checkout --detach vX.Y.Z
cp /path/to/.env.production /opt/mdr_app/.env
```

Update domain in Caddy config:

- Edit `/opt/mdr_app/docker/Caddyfile`
- Replace `your-domain.com` with your real domain.

Start stack:

```bash
cd /opt/mdr_app
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
docker compose ps
```

## 5) Windows Firewall

Open elevated PowerShell on Windows host:

```powershell
New-NetFirewallRule -DisplayName "MDR-HTTP-80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "MDR-HTTPS-443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
New-NetFirewallRule -DisplayName "MDR-BLOCK-8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Block
New-NetFirewallRule -DisplayName "MDR-BLOCK-5432" -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Block
```

## 6) DNS + TLS

Set DNS:

- `A` record for your domain -> server public IP

Caddy obtains certificates automatically once:

- domain resolves correctly
- ports 80/443 are reachable

Check TLS logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs -f caddy
```

## 7) Post-Deploy Checks

From Ubuntu (local container check):

```bash
curl -f http://127.0.0.1:8000/api/v1/health
```

Public checks:

```bash
curl -I https://your-domain.com
curl -f https://your-domain.com/api/v1/health
```

Create/update admin:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec web python create_admin.py
```

UI sanity:

- login
- dashboard
- a write flow
- correspondence form loads dropdowns correctly

## 8) Acceptance Tests

Smoke:

- `/api/v1/health` is OK
- login works
- write operation works

Correspondence settings E2E:

- follow `docs/manual_e2e_correspondence_settings.md`

Minimal regression:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec web pytest -q tests/test_regressions.py
```

## 9) Auto-Start After Reboot

Register startup scheduled task from elevated PowerShell:

```powershell
wsl -d Ubuntu-22.04 --cd /opt/mdr_app -e sh -lc "docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d"
```

Keep `restart: unless-stopped` for containers.

## 10) Upgrade Procedure (Tag Pull)

1. Push new tag from desktop.
2. On server backup DB:

```bash
docker exec -t mdr_postgres pg_dump -U mdr -d mdr_app -Fc > /opt/mdr_app/backup_$(date +%F_%H%M).dump
```

3. Deploy new tag:

```bash
cd /opt/mdr_app
git fetch origin --tags --prune
git checkout --detach vX.Y.Z
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
```

4. Run health + smoke checks.

## 11) Rollback Procedure

Trigger rollback on:

- health failure
- login failure
- critical write-path failure

Code rollback:

- checkout previous tag and rebuild:

```bash
cd /opt/mdr_app
git checkout --detach vPREVIOUS
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
```

Data rollback (if needed):

```bash
cat /opt/mdr_app/<backup>.dump | docker exec -i mdr_postgres pg_restore -U mdr -d mdr_app --clean --if-exists
```

Then validate:

- `/api/v1/health`
- login
- smoke write

## Security Notes

- Keep secrets only in server-side `.env` files, never in git.
- Use read-only deploy keys for server repo access.
- Rotate any exposed/pasted tokens immediately.
- Keep `DEBUG=false` and a strong `SECRET_KEY` in production.
