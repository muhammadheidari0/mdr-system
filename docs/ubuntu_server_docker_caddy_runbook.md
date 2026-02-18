# Ubuntu Server + Docker + Caddy Runbook (Production)

This runbook deploys MDR App on a direct Ubuntu Server host (no Windows/WSL).

## Release Anchor (Current Stable)

- Repository: `git@github.com:muhammadheidari0/mdr-system.git`
- Branch: `main`
- Stable tag: `v3.2.0`
- Commit: `d106bddddc3b34bd1d46fc8ed7ad20d641c1ee5b`

## Target Architecture

- Host OS: Ubuntu Server 22.04/24.04 LTS
- Runtime: Docker Engine + Compose plugin
- Reverse proxy + TLS: Caddy container
- Database: PostgreSQL container
- Public ports: `80`, `443`
- Local-only ports: `127.0.0.1:8000`, `127.0.0.1:5432`
- Deploy model: Git tag pull (`git fetch --tags`, `git checkout --detach <tag>`)
- Frontend build model: Docker multi-stage (no `static/dist` dependency in Git)

## 1) One-Time Server Preparation

Run as a sudo-enabled user:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release git openssh-client ufw
```

Install Docker Engine + Compose plugin:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Re-login, then:

```bash
sudo systemctl enable --now docker
docker --version
docker compose version
```

## 2) SSH Deploy Key for GitHub

Generate key:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/mdr_deploy -C "mdr-prod-ubuntu"
cat ~/.ssh/mdr_deploy.pub
```

Add this public key to GitHub as a read-only Deploy Key for the repo.

Configure SSH client:

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

## 3) Prepare Paths + Checkout Stable Tag

```bash
sudo mkdir -p /opt/mdr_app
sudo mkdir -p /opt/mdr_data/{postgres,database,data_store,archive_storage,logs,backups}
sudo chown -R $USER:$USER /opt/mdr_app /opt/mdr_data
```

```bash
git clone git@github.com:muhammadheidari0/mdr-system.git /opt/mdr_app
cd /opt/mdr_app
git fetch origin --tags --prune
git checkout --detach v3.2.0
git rev-parse HEAD
```

Expected output:

`d106bddddc3b34bd1d46fc8ed7ad20d641c1ee5b`

## 4) Configure Production `.env`

Create env file:

```bash
cd /opt/mdr_app
cp .env.production.example .env
```

Set required values in `.env`:

- `APP_ENV=production`
- `DEBUG=false`
- `SECRET_KEY=<long-random-secret>`
- `POSTGRES_PASSWORD=<strong-password>`
- `DATABASE_URL=postgresql+psycopg://mdr:<strong-password>@postgres:5432/mdr_app`
- `COMPOSE_DATABASE_URL=postgresql+psycopg://mdr:<strong-password>@postgres:5432/mdr_app`
- `MDR_DOMAIN=<your-public-domain>`
- `MDR_DATA_ROOT=/opt/mdr_data`
- `POSTGRES_PORT_BIND=127.0.0.1:5432:5432`
- `WEB_PORT_BIND=127.0.0.1:8000:8000`
- `APP_UID=1000`, `APP_GID=1000`
- `WEB_CONCURRENCY=2`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_FULL_NAME`

If integrations are enabled, also set:

- `GDRIVE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_SHARED_DRIVE_ID`
- `OPENPROJECT_BASE_URL`
- `OPENPROJECT_API_TOKEN`
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- (optional legacy) `OPENPROJECT_DEFAULT_PROJECT_ID`

## 5) Configure Caddy Domain + Deploy

Set `MDR_DOMAIN` in `.env` (for example: `MDR_DOMAIN=esms.example.com`).

Deploy:

```bash
cd /opt/mdr_app
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml ps
```

Initial logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs --tail=200 web
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs --tail=200 worker
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs --tail=200 caddy
```

## 6) Firewall + DNS + TLS

Configure UFW:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp
sudo ufw deny 5432/tcp
sudo ufw enable
sudo ufw status verbose
```

DNS:

- Create/update `A` record for the domain to server public IP.

TLS:

- Caddy issues certificates automatically when DNS and ports are correct.

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml logs -f caddy
```

## 7) Post-Deploy Gate

Health checks:

```bash
curl -f http://127.0.0.1:8000/api/v1/health
curl -I https://your-domain.com
curl -f https://your-domain.com/api/v1/health
```

Create/update admin:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec web python create_admin.py
```

UI smoke checklist:

- login
- dashboard
- one write operation
- correspondence form and dropdowns

## 8) Upgrade (Tag Pull)

Use helper script:

```bash
cd /opt/mdr_app
chmod +x update.sh
./update.sh vX.Y.Z
```

`update.sh` workflow:

1. fetch tags
2. backup DB
3. checkout target tag
4. compose rebuild/up
5. local health check

## 9) Rollback

Rollback code:

```bash
cd /opt/mdr_app
git checkout --detach <PREVIOUS_TAG>
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build
```

Rollback DB (if required):

```bash
cat /opt/mdr_data/backups/<backup>.dump | docker exec -i mdr_postgres pg_restore -U mdr -d mdr_app --clean --if-exists
```

Validate rollback:

- `/api/v1/health`
- login
- write smoke

## 10) Acceptance Criteria

1. `docker compose config` is valid.
2. `web` and `postgres` are localhost-only (`127.0.0.1` bindings).
3. Services survive reboot (`restart: unless-stopped` + `docker.service`).
4. UI/API smoke passes.
5. Regression check passes:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec web pytest -q tests/test_regressions.py
```
