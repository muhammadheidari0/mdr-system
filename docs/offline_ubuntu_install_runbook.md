# Ubuntu Offline Install Runbook

This runbook installs MDR from a prebuilt offline package on Ubuntu Server 24.04 when Docker Engine and the Compose plugin are already available on the host.

## Package Contents

Expected package name:

```bash
mdr-offline-installer-vX.Y.Z.tar.gz
```

The extracted directory contains:

```text
install.sh
release_manifest.env
checksums.txt
bundle/
  release/
  images/
```

## 1. Build the Package on a Connected Machine

Run from the repository root:

```bash
bash tools/build_offline_installer.sh --version v3.2.0
```

Output:

```bash
dist/mdr-offline-installer-v3.2.0.tar.gz
```

## 2. Copy the Package to the Target Server

Example:

```bash
scp dist/mdr-offline-installer-v3.2.0.tar.gz ubuntu@server:/tmp/
```

## 3. Prepare Secret Files on the Server

Create one file per secret:

```bash
mkdir -p /tmp/mdr-secrets
printf '%s' 'CHANGE_ME_ADMIN_PASSWORD' > /tmp/mdr-secrets/admin_password.txt
printf '%s' 'CHANGE_ME_POSTGRES_PASSWORD' > /tmp/mdr-secrets/postgres_password.txt
printf '%s' 'CHANGE_ME_LONG_RANDOM_SECRET' > /tmp/mdr-secrets/secret_key.txt
```

For `--tls-mode custom`, also place the certificate and key on disk.

## 4. Extract and Install

```bash
cd /tmp
tar -xzf mdr-offline-installer-v3.2.0.tar.gz
cd mdr-offline-installer-v3.2.0
```

### HTTP-only (recommended default for internal/offline first rollout)

```bash
bash install.sh \
  --domain mdr.internal \
  --tls-mode http \
  --admin-email admin@mdr.internal \
  --admin-password-file /tmp/mdr-secrets/admin_password.txt \
  --postgres-password-file /tmp/mdr-secrets/postgres_password.txt \
  --secret-key-file /tmp/mdr-secrets/secret_key.txt
```

### Internal Caddy CA

```bash
bash install.sh \
  --domain mdr.internal \
  --tls-mode internal \
  --admin-email admin@mdr.internal \
  --admin-password-file /tmp/mdr-secrets/admin_password.txt \
  --postgres-password-file /tmp/mdr-secrets/postgres_password.txt \
  --secret-key-file /tmp/mdr-secrets/secret_key.txt
```

### Custom Internal Certificate

```bash
bash install.sh \
  --domain mdr.internal \
  --tls-mode custom \
  --tls-cert-file /tmp/mdr-secrets/server.crt \
  --tls-key-file /tmp/mdr-secrets/server.key \
  --admin-email admin@mdr.internal \
  --admin-password-file /tmp/mdr-secrets/admin_password.txt \
  --postgres-password-file /tmp/mdr-secrets/postgres_password.txt \
  --secret-key-file /tmp/mdr-secrets/secret_key.txt
```

### Public ACME

Only use this when DNS and ACME reachability are genuinely available:

```bash
bash install.sh \
  --domain mdr.example.com \
  --tls-mode public \
  --allow-public-acme \
  --admin-email admin@mdr.example.com \
  --admin-password-file /tmp/mdr-secrets/admin_password.txt \
  --postgres-password-file /tmp/mdr-secrets/postgres_password.txt \
  --secret-key-file /tmp/mdr-secrets/secret_key.txt
```

## 5. Verification

Local health:

```bash
curl -f http://127.0.0.1:8000/api/v1/health
```

External health:

```bash
curl -f http://mdr.internal/api/v1/health
```

For `internal` and `custom`, HTTPS verification on clients depends on trusting the corresponding CA or certificate chain.
