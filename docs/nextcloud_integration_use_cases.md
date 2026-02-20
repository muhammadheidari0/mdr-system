# Nextcloud Integration Use Cases (MVP)

## Scope
- Provider: `Nextcloud` in `Settings > Integrations`
- Auth mode: `WebDAV + App Password`
- Mirror strategy: `single active provider`
- MVP behavior:
  - file mirror only
  - no OpenProject link enqueue when provider is `nextcloud`
  - no legacy backfill

## Architecture
1. Admin configures Nextcloud in Integrations:
  - `enabled`
  - `base_url`
  - `username`
  - `app_password` (write-only)
  - `root_path`
  - `skip_ssl_verify` (optional)
2. Runtime resolves credentials and TLS policy:
  - precedence: `env force > UI setting > env default`
3. Upload hooks set mirror plan:
  - provider `none` => `mirror_status=disabled`
  - provider `nextcloud` + valid config => `mirror_status=pending` + enqueue job
4. Worker processes `nextcloud_mirror` jobs and uploads via WebDAV.

## Structured Remote Path
- Archive:
  - `{root_path}/archive/{project_code}/{discipline_code}/{yyyy}/{mm}/{file_name}`
- Correspondence:
  - `{root_path}/correspondence/{project_code}/{discipline_code}/{yyyy}/{mm}/{file_name}`
- Comm Items:
  - `{root_path}/comm-items/{project_code}/{discipline_code}/{item_type}/{yyyy}/{mm}/{file_name}`

Fallback rules:
- Missing metadata => `unknown`
- file names are sanitized and uniqueness is enforced with timestamp/id prefix.

## Use Cases
1. Configure and verify connection
  - Save Nextcloud settings
  - Run `Test Nextcloud Connection`
  - check `reachable/auth_ok/status_code` summary
2. Archive mirror
  - upload new archive file
  - verify `mirror_status=pending`
  - run `Run Nextcloud Sync`
  - verify `mirror_status=mirrored` and `mirror_remote_url` exists
3. Correspondence attachment mirror
  - upload attachment in correspondence module
  - run Nextcloud sync
  - verify mirrored fields are populated
4. Comm item attachment mirror
  - upload attachment in comm-items
  - run Nextcloud sync
  - verify mirrored fields are populated

## Operational Notes
- Use a dedicated integration account in Nextcloud.
- For production, keep TLS verification enabled.
- `skip_ssl_verify` is only for internal/test environments.
- Secrets are not returned by settings API and are redacted in audit/logs.

## Limitations (MVP)
- No migration/backfill for old file rows.
- No direct document management integration beyond mirror metadata.
- No OpenProject linking in Nextcloud provider mode.
