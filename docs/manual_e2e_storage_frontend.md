# Manual E2E - Storage Management UX V1 (Workflow Focus)

## Scope
- Settings > Storage Management (3-step workflow):
  - Step 1: Paths
  - Step 2: Policy
  - Step 3: Integrations + Sync
- Quick regression check for other settings tabs.

## Out of Scope (V1)
- Backend contract changes (all checks use existing APIs).
- For full Site Cache scenarios, use `docs/manual_e2e_site_cache.md`.

## Preconditions
- Admin user is available.
- API `/api/v1/health` is OK.
- Browser cache is clear.
- User has access to `Settings`.

## 1) Open Storage Management
1. Open `Settings`.
2. Open `Storage Management` (top nav card).
3. Confirm Step 1 is active by default.

Expected:
- Storage page opens on `Paths`.
- Stepper is visible with 3 steps.

## 2) Stepper Navigation + Unsaved Guard
1. In Step 1, edit one path field (do not save).
2. Click Step 2 button, or `Next Step`.

Expected:
- Unsaved confirmation dialog appears.
- Choosing `Cancel` keeps user in current step.
- Choosing `OK` moves to next step.

## 3) Step 1 - Paths
1. Set `MDR path` and `Correspondence path` to different values.
2. Confirm normalized preview updates live under each input.
3. Set both paths equal (same value).

Expected:
- Inline red conflict error appears immediately.
- Both fields show error style.

4. Set different values again.
5. Click `Save Paths`.

Expected:
- Save succeeds without full page reload.
- Success note appears in same step.
- `Last saved` timestamp is updated.

## 4) Step 2 - Policy Presets + Numeric Sizes
1. Go to Step 2.
2. Click preset `Warning`, then `Standard`, then `Strict`.

Expected:
- Mode, blocked extensions, allowed MIME and size fields update each time.

3. Edit numeric size fields:
  - PDF (MB)
  - Native (MB)
  - Attachment (MB)
4. Save policy.
5. Refresh page and return to Storage Management Step 2.

Expected:
- Saved values are reloaded correctly.
- Max size values persist as numbers (no raw JSON input in UI).

## 5) Step 3 - Integrations + Sync
1. Go to Step 3.
2. Toggle `Google Drive` OFF.

Expected:
- Google Drive dependent input is disabled.
- `Run Google Drive Sync` button is disabled.

3. Toggle `OpenProject` OFF.

Expected:
- OpenProject default WP input is disabled.
- `Run OpenProject Sync` button is disabled.

4. Re-enable providers and click `Save Integrations`.

Expected:
- Save success message is shown.

5. Click `Run Google Drive Sync`.
6. Click `Run OpenProject Sync`.

Expected:
- Result panel first shows in-progress text.
- Then final state is visible as success or error.
- Error case should show friendly text plus short technical detail.

## 6) Action Bar Behavior
1. In each step, verify bottom sticky action bar is visible:
  - `Previous Step`
  - `Next Step`
  - `Save Current Step`
2. Verify:
  - In Step 1, `Previous` is disabled.
  - In Step 3, `Next` is disabled.

Expected:
- Buttons state matches current step.
- Save action stores the current step only.

## 7) Regression - General Settings Tabs
1. Open `General > DB Sync`.
2. Open `General > Projects`.
3. Open `Correspondence > Issuing`.
4. Open `Correspondence > Categories`.
5. Open `MDR > Disciplines/Packages`.

Expected:
- Tabs load without JS errors.
- Existing CRUD behavior is unchanged.

## 8) Final Smoke
1. Login
2. Open Settings
3. Complete one full pass: Paths -> Policy -> Integrations
4. Save each step

Expected:
- No generic `Error` dialogs.
- No broken tab navigation.
