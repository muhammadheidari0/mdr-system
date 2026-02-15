# Manual E2E Scenario - Correspondence Parameter Settings

Date: 2026-02-15
Scope: General Settings -> Correspondence parameters (Issuing Entity / Correspondence Category) and reflection in Correspondence form dropdowns.

## Preconditions
- User role: System Administrator (has access to Settings and Correspondence).
- App is running and database is reachable.
- Navigate to: Settings -> General Settings.

## Test Data
- Issuing code: `ZZ`
- Issuing name (EN): `ZZ Test Issuing`
- Issuing name (FA): `مرجع تست ZZ`
- Category code: `ZZC`
- Category name (EN): `ZZ Test Category`
- Category name (FA): `دسته تست ZZ`

## Case 1 - Add Issuing Entity
1. Open `General Settings`.
2. Click top module button `مکاتبات`.
3. Open page `مراجع صدور`.
4. Fill form with test issuing values.
5. Save.

Expected:
- Success message is shown.
- New row appears in issuing list.
- Row is `active`.

## Case 2 - Add Correspondence Category
1. Stay in module `مکاتبات`.
2. Open page `دسته های مکاتبات`.
3. Fill form with test category values.
4. Save.

Expected:
- Success message is shown.
- New row appears in category list.
- Row is `active`.

## Case 3 - Reflection in Correspondence Form
1. Go to Correspondence module.
2. Open `New Correspondence` form.
3. Open dropdown `مرجع صدور`.
4. Open dropdown `دسته`.

Expected:
- `ZZ Test Issuing` is present in issuing dropdown.
- `ZZ Test Category` is present in category dropdown.
- Selecting them affects reference preview pattern as expected.

## Case 4 - Edit Issuing Entity
1. Return to Settings -> General -> `مراجع صدور`.
2. Edit `ZZ` record and change EN name to `ZZ Test Issuing v2`.
3. Save.

Expected:
- Row updates in list.
- In Correspondence form dropdown, label reflects `v2` after refresh.

## Case 5 - Disable Issuing Entity
1. In `مراجع صدور`, disable `ZZ`.
2. Refresh Correspondence form.

Expected:
- `ZZ` does not appear in issuing dropdown (catalog returns only active items).
- Existing correspondences that already used `ZZ` remain intact.

## Case 6 - Disable Correspondence Category
1. In `دسته های مکاتبات`, disable `ZZC`.
2. Refresh Correspondence form.

Expected:
- `ZZC` does not appear in category dropdown.
- Existing correspondences with `ZZC` remain intact.

## Case 7 - Re-enable Flow (Optional)
1. Edit disabled rows and set `active=true`.
2. Refresh Correspondence form.

Expected:
- Re-enabled items are visible again in dropdowns.

## Negative Checks
- Try creating issuing with unknown project code.
  - Expected: API validation error (`Project not found`).
- Try hard-delete issuing/category that is already referenced.
  - Expected: conflict error (`409`) due FK usage.

## Pass Criteria
- All Add/Edit/Disable actions work from Settings.
- Dropdowns in Correspondence form always reflect active records.
- No UI/console errors during flow.
