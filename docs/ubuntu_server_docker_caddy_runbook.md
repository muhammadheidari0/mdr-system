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

## Quick Bootstrap (Recommended)

Use the bootstrap script for first-time Ubuntu 24.04 setup + deploy:

```bash
cd /opt/mdr_app
chmod +x tools/bootstrap_ubuntu2404.sh
tools/bootstrap_ubuntu2404.sh \
  --domain esms.example.com \
  --admin-email admin@esms.example.com \
  --admin-password 'CHANGE_ME_STRONG_ADMIN_PASSWORD' \
  --postgres-password 'CHANGE_ME_STRONG_PASSWORD' \
  --secret-key 'CHANGE_ME_LONG_RANDOM_SECRET'
```

If you intentionally need a clean PostgreSQL re-init:

```bash
tools/bootstrap_ubuntu2404.sh ... --reset-db
```

Key flags:

- `--repo-url` (default `git@github.com:muhammadheidari0/mdr-system.git`)
- `--ref` (default `v3.2.0`)
- `--app-dir` (default `/opt/mdr_app`)
- `--data-root` (default `/opt/mdr_data`)
- `--skip-ufw`
- `--existing-repo`
- `--reset-db` (destructive: removes compose volumes + purges `${MDR_DATA_ROOT}/postgres`)
- `--dry-run`

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
- `MDR_DOMAIN=<public-domain-or-ipv4>`
- `MDR_DATA_ROOT=/opt/mdr_data`
- `STORAGE_ALLOWED_ROOTS=/app/archive_storage,/app/data_store`
- `STORAGE_REQUIRE_ABSOLUTE_PATHS=true`
- `STORAGE_VALIDATE_WRITABLE_ON_SAVE=true`
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
- `OPENPROJECT_TLS_VERIFY` (default `true`)
- `OPENPROJECT_TLS_VERIFY_FORCE` (optional override)
- `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- (optional legacy) `OPENPROJECT_DEFAULT_PROJECT_ID`

## 4.1) Network Mount for Archive Storage

Use host-level mount (CIFS/NFS), then bind it into container paths configured in compose.

Example host mount points:

- `/opt/mdr_data/archive_storage`
- `/opt/mdr_data/data_store`

Operational rules:

- Never configure `smb://...` paths in app settings.
- Save only absolute storage paths inside container, for example:
  - `/app/archive_storage/technical`
  - `/app/archive_storage/correspondence`
- `Save Storage Paths` returns `422` when a path is relative, خارج از `STORAGE_ALLOWED_ROOTS`, or not writable.

## 5) Configure Caddy Mode + Deploy

Set `MDR_DOMAIN` in `.env`:

- Domain example: `MDR_DOMAIN=esms.example.com` (auto HTTPS)
- IPv4 example: `MDR_DOMAIN=185.231.181.48` (HTTP-only on `:80`)

Render Caddyfile from templates (recommended before deploy):

```bash
cd /opt/mdr_app
bash tools/render_caddyfile.sh --domain "$(grep '^MDR_DOMAIN=' .env | cut -d= -f2)" --output /opt/mdr_app/docker/Caddyfile.generated
```

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
curl -I http://185.231.181.48
curl -f http://185.231.181.48/api/v1/health
# if MDR_DOMAIN is a real domain:
curl -I https://your-domain.com
curl -f https://your-domain.com/api/v1/health
```

Create/update admin:

```bash
docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml exec -T \
  -e ADMIN_EMAIL="$(grep '^ADMIN_EMAIL=' .env | cut -d= -f2)" \
  -e ADMIN_PASSWORD="$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2)" \
  -e ADMIN_FULL_NAME="$(grep '^ADMIN_FULL_NAME=' .env | cut -d= -f2)" \
  web python create_admin.py
```

`bootstrap_ubuntu2404.sh` now runs this admin sync automatically after services become healthy.

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
# or deploy latest semantic tag:
./update.sh --latest
```

`update.sh v2` workflow:

1. pre-flight checks:
   - docker permission (`docker info` / `sudo -n docker info`)
   - disk guard (default minimum 10 GB)
   - `.env` contract validation
2. auto-stash local changes (kept for audit)
3. force checkout target tag (`git checkout -f --detach`)
4. mandatory DB backup before deploy
5. render smart Caddyfile from `MDR_DOMAIN`
6. compose rebuild/up
7. local health check (rollback trigger)
8. public health check (warning only)

Useful flags:

- `--min-free-gb <N>`
- `--dry-run`
- `--no-auto-rollback`

## 9) Rollback

Manual rollback to latest successful deployed session:

```bash
cd /opt/mdr_app
./update.sh --rollback
```

Manual rollback to specific session:

```bash
cd /opt/mdr_app
./update.sh --rollback --session-id <SESSION_ID>
```

`update.sh --rollback` restores both:

1. code (`previous_commit` stored in session metadata)
2. database dump captured before that deploy

Session metadata location:

- `/opt/mdr_data/backups/update_sessions/*.env`

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
