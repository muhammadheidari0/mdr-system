# Native EDMS Cutover Runbook

1. Export master data snapshot.
2. Push sync events into native Nextcloud EDMS.
3. Export archive manifest.
4. Import archive rows into Team Folder storage.
5. Run parity report.
6. Switch old archive flow to read-only.
7. Enable native archive writes.
