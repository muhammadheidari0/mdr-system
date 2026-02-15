# Manual E2E - Site Cache (HQ -> Site, Archive-only)

## Scope
- Settings > General > Site Cache
- Agent sync (`tools/mdr_sync_agent.py`)
- Archive local-first behavior

## Preconditions
- Admin user exists.
- API health is OK.
- At least one archive file exists in a project visible to admin.
- Database migrated to include site cache tables.

## 1) Profile CRUD
1. Open `Settings > General > DB`.
2. In `Site Cache` section create profile:
   - code: `SITE_A`
   - name: `Site A`
   - local root path: sample UNC/local path
   - fallback mode: `local_first`
3. Save and verify row appears in profile table.
4. Edit profile and change name/root, save again.
5. Disable profile and verify it is marked inactive.

Expected:
- Add/Edit/Disable works with success feedback.

## 2) CIDR + Rule + Token
1. Select profile in the right panel.
2. Add CIDR (example `10.88.0.0/16`).
3. Add rule (example statuses `IFA,IFC`, primary-only, latest-only).
4. Mint token and copy token value immediately.
5. Revoke token and verify it disappears from active token list.

Expected:
- Invalid CIDR is rejected with clear message.
- Token is shown once and revoke immediately blocks usage.

## 3) Rebuild Pins
1. With at least one matching archive file, click `Rebuild Pins`.
2. Confirm summary shows selected/enabled/disabled counts.
3. Call local-cache manifest for site scope (or use agent manifest endpoint) and verify pinned files exist.

Expected:
- Rebuild updates pinned set according to rules.

## 4) Agent Sync First Run
1. Run:
   ```bash
   python tools/mdr_sync_agent.py --base-url https://<domain> --site-code SITE_A --site-token <TOKEN> --out-dir /tmp/mdr_site_cache --max-workers 4
   ```
2. Verify files are downloaded and `manifest.local.json` is created.
3. Verify heartbeat timestamp updates in profile state (API/UI).

Expected:
- First run downloads matching files.

## 5) Agent Sync Second Run (Skip by Hash)
1. Run same command again.
2. Verify summary shows high `skipped` and no unnecessary downloads.

Expected:
- Existing unchanged files are skipped by hash.

## 6) Prune Reconcile
1. Change rule set so one file is no longer pinned.
2. Rebuild pins in UI.
3. Run agent with prune:
   ```bash
   python tools/mdr_sync_agent.py --base-url https://<domain> --site-code SITE_A --site-token <TOKEN> --out-dir /tmp/mdr_site_cache --prune
   ```

Expected:
- Files removed from manifest are pruned locally.

## 7) Archive Local-First
1. Access Archive from an IP that matches the profile CIDR.
2. Open row actions and click `Open Local`.
3. If browser blocks `file://`, verify UNC/local path copy fallback message.
4. Click download button and verify local-first attempt happens before HQ fallback.

Expected:
- Site users get local-open path first.
- Fallback to HQ still works.

## 8) Outside Site Network
1. Access Archive from non-matching IP.
2. Verify `Open Local` action does not appear.
3. Verify normal HQ download remains functional.

Expected:
- Backward compatibility for non-site users.

## 9) Security Checks
1. Call `GET /api/v1/storage/site-manifest` without token.
2. Call with revoked token.
3. Call with wrong site_code + valid token from another site.

Expected:
- All unauthorized cases return `401`.

## 10) Non-Regression
1. Archive upload.
2. Archive revision history.
3. Archive pin/unpin (user scope).
4. Correspondence attachment flow.

Expected:
- Existing flows remain stable.
