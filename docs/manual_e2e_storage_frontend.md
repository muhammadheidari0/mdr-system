# Manual E2E - Storage Frontend (Archive + Correspondence + Settings)

## Scope
- Archive
- Correspondence (attachments)
- Settings > General (Storage Policy, Storage Integrations)

## Preconditions
- Admin user is available.
- API `/api/v1/health` is OK.
- At least one active project/document exists for archive upload.
- Browser cache is clear for current session.

## 1) Archive - Valid Upload + Status Badges
1. Open `Archive` page.
2. Upload a valid file (PDF or allowed type).
3. Confirm upload success message.
4. In file list row, confirm badges are visible:
   - `validation_status`
   - `mirror_status`
   - `openproject_sync_status`
5. Click `Integrity` action and verify details show:
   - `sha256`
   - `detected_mime`
   - validation and sync statuses.

Expected:
- No generic `Error` message.
- Friendly message is shown with exact detail if backend returns detail.

## 2) Archive - Rejected Upload (Magic/MIME mismatch)
1. Try uploading a file with allowed extension but invalid binary content.
2. Observe error toast/message.

Expected:
- Friendly Persian error text is shown.
- Backend detail is appended (`جزئیات: ...`).
- Request returns validation error (for example `422`).

## 3) Archive - Pin / Unpin
1. In archive list, click `Pin` for one file.
2. Refresh list.
3. Verify file stays pinned.
4. Click `Unpin`.
5. Refresh list again.

Expected:
- Button state changes immediately.
- Pinned state persists via manifest.

## 4) Correspondence - Attachment Upload + Status Badges
1. Open `Correspondence` and create or edit a correspondence record.
2. Upload an attachment.
3. In attachments table, verify columns:
   - Security / Sync badges
   - Pin action
4. Confirm badges display values for:
   - validation
   - drive mirror
   - openproject sync.

Expected:
- Upload succeeds without generic error.
- If upload fails, friendly + exact detail is shown.

## 5) Correspondence - Attachment Pin / Unpin
1. Click pin for one attachment.
2. Refresh or reopen workflow modal.
3. Verify pinned state remains.
4. Unpin and verify state updates.

Expected:
- Pin state uses local-cache manifest for `correspondence_attachment`.

## 6) Settings - Storage Policy
1. Open `Settings > General > DB`.
2. In `Storage Policy` card, change:
   - enforcement mode
   - blocked extensions
   - allowed mimes
   - max size json.
3. Save.
4. Refresh page.

Expected:
- Saved values reload correctly.
- No regression in other settings tabs.

## 7) Settings - Storage Integrations + Run Sync
1. In `Storage Integrations` card, toggle integration flags.
2. Save integrations.
3. Click `Run Google Drive Sync`.
4. Click `Run OpenProject Sync`.

Expected:
- Summary appears with `processed/success/failed/dead`.
- Success and failure states are visually distinct.

## 8) Non-Regression - Correspondence Settings Tabs
1. Open `Settings > General > corr_issuing`.
2. Add/Edit/Disable one row.
3. Open `Settings > General > corr_categories`.
4. Add/Edit/Disable one row.

Expected:
- Existing behavior remains unchanged.
- Changes reflect in correspondence form dropdowns.

## 9) Smoke Recheck
1. Login
2. Dashboard
3. Archive upload
4. Correspondence attachment upload
5. Settings save + run sync

Expected:
- All flows complete successfully.
- No generic error dialogs.
