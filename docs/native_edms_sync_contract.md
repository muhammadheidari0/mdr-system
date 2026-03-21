# Native EDMS Sync Contract

Native EDMS consumes signed event envelopes from MDR.

## Envelope
- `event_id`
- `entity`
- `operation`
- `version`
- `occurred_at`
- `source`
- `payload`
- `signature`

## Target Endpoints
- `/apps/edms/api/sync/projects`
- `/apps/edms/api/sync/catalogs`
- `/apps/edms/api/sync/organizations`
- `/apps/edms/api/sync/users`
- `/apps/edms/api/sync/permissions`
- `/apps/edms/api/sync/scopes`
