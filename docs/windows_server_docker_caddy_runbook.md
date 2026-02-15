# Windows Server + Docker + Caddy Runbook (Production)

This runbook deploys MDR App on Windows Server using Linux containers under WSL2.

## Target Architecture

- Host OS: Windows Server 2022+ (recommended)
- Runtime: WSL2 + Ubuntu 22.04 + Docker Engine
- Reverse proxy + TLS: Caddy container
- Database: PostgreSQL container
- Public ports: `80`, `443`
- Private/local-only ports: `8000`, `5432`

## 1) Desktop Release Steps

Run from your workstation:

```powershell
git checkout main
git pull --ff-only
npm run typecheck
npm run build
```

Create and push release tag:

```powershell
git tag -a v2.1.3 -m "Release: Windows Server + Docker baseline"
git push origin main
git push origin v2.1.3
```

Create release artifact:

```powershell
git archive --format=tar.gz --output mdr_app_v2.1.3.tar.gz v2.1.3
```

Prepare a production env file outside git, for example:

- `.env.production`

Transfer these files to Windows Server (example destination `C:\deploy\`):

- `mdr_app_v2.1.3.tar.gz`
- `.env.production`

## 2) One-Time Windows Server Preparation

Open **elevated PowerShell**:

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
sudo apt install -y ca-certificates curl gnupg lsb-release
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
```

## 3) Deploy Project on Server

Inside Ubuntu:

```bash
sudo mkdir -p /opt/mdr_app
sudo chown -R $USER:$USER /opt/mdr_app
cd /opt/mdr_app
tar -xzf /mnt/c/deploy/mdr_app_v2.1.3.tar.gz -C /opt/mdr_app
cp /mnt/c/deploy/.env.production /opt/mdr_app/.env
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

## 4) Windows Firewall

Use included helper script (elevated PowerShell):

```powershell
cd C:\deploy\mdr_app
.\docker\windows\Configure-MdrFirewall.ps1
```

This creates rules:

- Allow `80` / `443`
- Block `8000` / `5432` inbound

## 5) DNS + TLS

Set DNS:

- `A` record for your domain -> server public IP

Caddy obtains certificates automatically once:

- domain resolves correctly
- ports 80/443 are reachable

Check TLS logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs -f caddy
```

## 6) Post-Deploy Checks

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

## 7) Acceptance Tests

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

## 8) Auto-Start After Reboot

Register startup scheduled task from elevated PowerShell:

```powershell
cd C:\deploy\mdr_app
.\docker\windows\Register-MdrDockerStartupTask.ps1
```

Default task runs:

```text
wsl -d Ubuntu-22.04 --cd /opt/mdr_app -e sh -lc "docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d"
```

## 9) Upgrade Procedure

1. Build and send new artifact + env if needed.
2. Backup DB:

```bash
docker exec -t mdr_postgres pg_dump -U mdr -d mdr_app -Fc > /opt/mdr_app/backup_$(date +%F_%H%M).dump
```

3. Deploy new version:

```bash
tar -xzf /mnt/c/deploy/mdr_app_vX.Y.Z.tar.gz -C /opt/mdr_app
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
```

4. Run health + smoke checks.

## 10) Rollback Procedure

Trigger rollback on:

- health failure
- login failure
- critical write-path failure

Code rollback:

- redeploy previous artifact
- run `docker compose ... up -d --build`

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
- Rotate any exposed/pasted tokens immediately.
- Keep `DEBUG=false` and a strong `SECRET_KEY` in production.
