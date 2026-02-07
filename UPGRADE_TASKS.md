# Upgrade Tasks (Incremental)

## Phase A - Foundation (Separated Roots)
- [x] A1. Add settings API for storage paths (`GET/POST /api/v1/settings/storage-paths`).
- [x] A2. Add General Settings UI controls for `MDR` and `Correspondence` storage paths.
- [x] A3. Add regression test for storage-paths roundtrip.
- [x] A4. Add `StorageManager` service and read paths from DB settings.
- [x] A5. Refactor archive upload/download to use `StorageManager`.

## Phase B - Archive Upgrade (Dual Files + UX)
- [x] B1. Extend archive data model for dual file support (`pdf/native` companion files).
- [x] B2. Add dual-upload API endpoint and validation.
- [x] B3. Add archive table actions: `download pdf`, `download native`, `copy doc no`, `revision history`.
- [x] B4. Add archive filters: project, discipline, status, date, text search.

## Phase C - Correspondence Module
- [x] C1. Add `correspondence` table/model and migration-safe bootstrap.
- [x] C2. Add API: dashboard stats, list with filters, create/update.
- [x] C3. Implement race-safe auto reference generator (`ISSUING-CATEGORY-IN/OUT-YYMM###`).
- [x] C4. Add correspondence UI: dashboard cards, filters, table, create/edit modal (issuing/category centric).
- [x] C5. Add action tracking CRUD + correspondence file uploads (letter/original/attachment) in same modal.

## Phase D - Forms / Reports / Consultant
- [x] D0. Restructure sidebar into 3 main modules (EDMS, Contractor, Consultant) with module landing views.
- [ ] D1. Define dynamic form schema tables and submission tables.
- [ ] D2. Add contractor forms API + draft-save.
- [ ] D3. Add reporting endpoints (daily/weekly, export PDF/Excel).
- [ ] D4. Add consultant tools (checklists, defects, site notes, follow-up workflow).
- [ ] D5. Add notification pipeline (in-app first, then email/SMS adapters).

## Phase E - Access UX / Permissions
- [x] E0. Unify EDMS navigation into a single sidebar entry with in-page tabs.
- [ ] E1. Finish user scope status column + action menu in users table.
- [ ] E2. Matrix UX cleanup (single-row toolbar, grouping, sticky headers).
- [ ] E3. Move all scope editing to user access modal only.
- [ ] E4. Replace coarse role checks in critical routes with granular permission dependencies.
- [x] E5. Add role-based + last-selected default EDMS tab selection.
