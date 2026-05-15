// @ts-nocheck
// Archive page logic
import { formatShamsiDate, formatShamsiDateTime } from "../../lib/persian_datetime";
        let isFullMode = false;
        let allPackages = [];
        let allBlocks = [];
        let archiveFormDataCache = null;
        let archiveFormDataPromise = null;
        let archiveDropzonesBound = false;
        let archiveUiEventsBound = false;
        let archiveUiEventsRoot = null;
        let archiveDocSuggestTimer = null;
        let archiveFullPreviewTimer = null;
        let archiveSuspendAutoPreview = false;

        const ARCHIVE_OUTPUT_ALLOWED_EXTENSIONS = new Set([
            'pdf', 'dwf', 'dwfx', 'png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'gif', 'webp'
        ]);
        const ARCHIVE_NATIVE_BLOCKED_EXTENSIONS = new Set([
            'exe', 'msi', 'bat', 'cmd', 'ps1', 'vbs', 'js', 'jse', 'hta', 'scr', 'com', 'dll', 'reg'
        ]);
        const ARCHIVE_ENTITY_TYPE = 'archive_file';
        let archivePinnedSet = new Set();
        let archiveSiteContext = {
            loaded: false,
            active: false,
            siteCode: '',
            siteScope: '',
            localRootPath: '',
            fallbackMode: 'local_first',
            matchedCidr: '',
        };
        const ARCHIVE_VALIDATION_BADGES = {
            valid: { cls: 'storage-badge is-valid', label: 'Valid' },
            warning: { cls: 'storage-badge is-warning', label: 'Needs review' },
            rejected: { cls: 'storage-badge is-rejected', label: 'Rejected' },
            legacy: { cls: 'storage-badge is-legacy', label: 'Legacy' },
            default: { cls: 'storage-badge is-legacy', label: '-' },
        };
        const ARCHIVE_MIRROR_BADGES = {
            mirrored: { cls: 'storage-badge is-synced', label: 'Drive: synced' },
            synced: { cls: 'storage-badge is-synced', label: 'Drive: synced' },
            pending: { cls: 'storage-badge is-pending', label: 'Drive: pending' },
            queued: { cls: 'storage-badge is-pending', label: 'Drive: queued' },
            failed: { cls: 'storage-badge is-failed', label: 'Drive: failed' },
            disabled: { cls: 'storage-badge is-disabled', label: 'Drive: disabled' },
            not_linked: { cls: 'storage-badge is-disabled', label: 'Drive: not linked' },
            default: { cls: 'storage-badge is-disabled', label: 'Drive: -' },
        };
        const ARCHIVE_OPENPROJECT_BADGES = {
            synced: { cls: 'storage-badge is-synced', label: 'OpenProject: synced' },
            pending: { cls: 'storage-badge is-pending', label: 'OpenProject: pending' },
            failed: { cls: 'storage-badge is-failed', label: 'OpenProject: failed' },
            disabled: { cls: 'storage-badge is-disabled', label: 'OpenProject: disabled' },
            not_linked: { cls: 'storage-badge is-disabled', label: 'OpenProject: not linked' },
            default: { cls: 'storage-badge is-disabled', label: 'OpenProject: -' },
        };

        function archiveToFileUrl(pathValue) {
            const normalized = String(pathValue || '').replace(/\\/g, '/');
            if (!normalized) return '';
            if (normalized.startsWith('//')) {
                return `file:${encodeURI(normalized)}`;
            }
            return `file:///${encodeURI(normalized)}`;
        }

        function archiveBuildLocalPath(relativePath) {
            const root = String(archiveSiteContext?.localRootPath || '').trim();
            const rel = String(relativePath || '').trim();
            if (!root || !rel) return '';
            const rootNoSlash = root.replace(/[\\/]+$/g, '');
            const relNoSlash = rel.replace(/^[\\/]+/g, '');
            return `${rootNoSlash}\\${relNoSlash.replace(/\//g, '\\')}`;
        }

        async function archiveTryOpenLocal(relativePath, fileName = '') {
            const localPath = archiveBuildLocalPath(relativePath);
            if (!localPath) return false;
            const fileUrl = archiveToFileUrl(localPath);
            if (!fileUrl) return false;
            try {
                const opened = window.open(fileUrl, '_blank');
                if (opened) {
                    return true;
                }
            } catch (_) {}
            try {
                await navigator.clipboard.writeText(localPath);
                alert(`مسیر محلی باز نشد. مسیر کپی شد:\n${localPath}`);
            } catch (_) {
                alert(`مسیر محلی:\n${localPath}`);
            }
            return false;
        }

        async function archiveLoadSiteContext(projectCode = '', force = false) {
            if (archiveSiteContext.loaded && !force) return archiveSiteContext;
            const params = new URLSearchParams();
            const project = String(projectCode || '').trim();
            if (project) params.set('project_code', project);
            const url = `/api/v1/storage/site-context${params.toString() ? `?${params.toString()}` : ''}`;
            try {
                const payload = await archiveRequestJson(url);
                const profile = payload?.profile || {};
                archiveSiteContext = {
                    loaded: true,
                    active: Boolean(payload?.site_active),
                    siteCode: String(profile?.code || ''),
                    siteScope: String(payload?.site_scope || ''),
                    localRootPath: String(profile?.local_root_path || ''),
                    fallbackMode: String(profile?.fallback_mode || 'local_first'),
                    matchedCidr: String(payload?.matched_cidr || ''),
                };
                return archiveSiteContext;
            } catch (error) {
                console.error('Failed to load site context', error);
                archiveSiteContext = {
                    loaded: true,
                    active: false,
                    siteCode: '',
                    siteScope: '',
                    localRootPath: '',
                    fallbackMode: 'local_first',
                    matchedCidr: '',
                };
                return archiveSiteContext;
            }
        }

        async function archiveReadJsonSafe(response) {
            try {
                return await response.json();
            } catch (_) {
                return null;
            }
        }

        async function archiveRequestJson(url, init = null) {
            const response = await window.fetchWithAuth(url, init || undefined);
            const payload = await archiveReadJsonSafe(response);
            if (!response.ok || !payload?.ok) {
                const detail = String(payload?.detail || payload?.message || `Request failed (${response.status})`).trim();
                const error = new Error(detail || `Request failed (${response.status})`);
                error.statusCode = Number(response.status || 0);
                error.detail = detail;
                throw error;
            }
            return payload;
        }

        function archiveStatusBadge(metaMap, statusValue) {
            const key = String(statusValue || '').trim().toLowerCase();
            const meta = metaMap[key] || metaMap.default;
            return `<span class="${meta.cls}">${archiveEsc(meta.label)}</span>`;
        }

        function archiveStatusLabel(metaMap, statusValue) {
            const key = String(statusValue || '').trim().toLowerCase();
            const meta = metaMap[key] || metaMap.default;
            return String(meta?.label || '-');
        }

        function archiveValidationTone(statusValue) {
            const key = String(statusValue || '').trim().toLowerCase();
            if (key === 'valid') return 'success';
            if (key === 'warning') return 'warning';
            if (key === 'rejected') return 'error';
            return 'muted';
        }

        function archiveSyncTone(statusValue) {
            const key = String(statusValue || '').trim().toLowerCase();
            if (key === 'synced' || key === 'mirrored') return 'success';
            if (key === 'pending' || key === 'queued') return 'syncing';
            if (key === 'failed') return 'error';
            return 'muted';
        }

        function archiveBuildSecurityIcons(fileRow) {
            const validationLabel = archiveStatusLabel(ARCHIVE_VALIDATION_BADGES, fileRow?.validation_status);
            const mirrorLabel = archiveStatusLabel(ARCHIVE_MIRROR_BADGES, fileRow?.mirror_status);
            const openprojectLabel = archiveStatusLabel(
                ARCHIVE_OPENPROJECT_BADGES,
                fileRow?.openproject_sync_status
            );
            const mirrorTime = fileRow?.mirror_updated_at
                ? `\nLast update: ${formatShamsiDateTime(fileRow.mirror_updated_at)}`
                : '';
            const openprojectTime = fileRow?.openproject_last_synced_at
                ? `\nLast update: ${formatShamsiDateTime(fileRow.openproject_last_synced_at)}`
                : '';
            const validationTone = archiveValidationTone(fileRow?.validation_status);
            const mirrorTone = archiveSyncTone(fileRow?.mirror_status);
            const openprojectTone = archiveSyncTone(fileRow?.openproject_sync_status);
            const mirrorSpin = mirrorTone === 'syncing' ? ' archive-sync-spin' : '';
            const openprojectSpin = openprojectTone === 'syncing' ? ' archive-sync-spin' : '';
            return `
                <div class="archive-sync-icons">
                    <span class="archive-sync-icon archive-sync-icon--${validationTone}" title="${archiveEsc(`Validation: ${validationLabel}`)}">
                        <span class="material-icons-round">verified</span>
                    </span>
                    <span class="archive-sync-icon archive-sync-icon--${mirrorTone}" title="${archiveEsc(`Google Drive: ${mirrorLabel}${mirrorTime}`)}">
                        <span class="material-icons-round${mirrorSpin}">cloud</span>
                    </span>
                    <span class="archive-sync-icon archive-sync-icon--${openprojectTone}" title="${archiveEsc(`OpenProject: ${openprojectLabel}${openprojectTime}`)}">
                        <span class="material-icons-round${openprojectSpin}">hub</span>
                    </span>
                </div>`;
        }

        function archiveFriendlyUploadMessage(error) {
            const statusCode = Number(error?.statusCode || 0);
            const detail = String(error?.detail || error?.message || '').trim();
            const lower = detail.toLowerCase();
            let friendly = 'Ø®Ø·Ø§ Ø¯Ø± Ø¢Ù¾Ù„ÙˆØ¯ ÙØ§ÛŒÙ„.';
            if (statusCode === 413 || lower.includes('too large') || lower.includes('size')) {
                friendly = 'Ø­Ø¬Ù… ÙØ§ÛŒÙ„ Ø¨ÛŒØ´ØªØ± Ø§Ø² Ø­Ø¯ Ù…Ø¬Ø§Ø² Ø§Ø³Øª.';
            } else if (lower.includes('magic') || lower.includes('mime') || lower.includes('content type')) {
                friendly = 'Ù†ÙˆØ¹ ÙˆØ§Ù‚Ø¹ÛŒ ÙØ§ÛŒÙ„ Ø¨Ø§ ÙØ±Ù…Øª Ù…Ø¬Ø§Ø² ØªØ·Ø§Ø¨Ù‚ Ù†Ø¯Ø§Ø±Ø¯.';
            } else if (lower.includes('blocked extension') || lower.includes('extension')) {
                friendly = 'Ù¾Ø³ÙˆÙ†Ø¯ ÙØ§ÛŒÙ„ Ù…Ø¬Ø§Ø² Ù†ÛŒØ³Øª.';
            } else if (lower.includes('validation') || lower.includes('invalid')) {
                friendly = 'ÙØ§ÛŒÙ„ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª ÛŒØ§ Ø¨Ø§ Ø³ÛŒØ§Ø³Øª Ø§Ù…Ù†ÛŒØªÛŒ Ø³Ø§Ø²Ú¯Ø§Ø± Ù†ÛŒØ³Øª.';
            } else if (lower.includes('document') || lower.includes('revision')) {
                friendly = 'Ø«Ø¨Øª ÙØ§ÛŒÙ„ Ø±ÙˆÛŒ Ù…Ø¯Ø±Ú© Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡ Ø§Ù†Ø¬Ø§Ù… Ù†Ø´Ø¯.';
            }
            return detail ? `${friendly}\nØ¬Ø²Ø¦ÛŒØ§Øª: ${detail}` : friendly;
        }

        async function archiveLoadPinManifest() {
            try {
                const payload = await archiveRequestJson(
                    '/api/v1/storage/local-cache/manifest?entity_type=archive_file&only_pinned=true'
                );
                const items = Array.isArray(payload?.items) ? payload.items : [];
                archivePinnedSet = new Set(
                    items
                        .map((item) => Number(item?.file_id || 0))
                        .filter((fileId) => Number.isFinite(fileId) && fileId > 0)
                );
            } catch (error) {
                console.error('Failed to load archive pin manifest', error);
                archivePinnedSet = new Set();
            }
        }

        async function archiveTogglePin(fileId, shouldPin) {
            const id = Number(fileId || 0);
            if (!id) return;
            const endpoint = shouldPin ? '/api/v1/storage/local-cache/pin' : '/api/v1/storage/local-cache/unpin';
            await archiveRequestJson(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_id: id, entity_type: ARCHIVE_ENTITY_TYPE }),
            });
            if (shouldPin) {
                archivePinnedSet.add(id);
            } else {
                archivePinnedSet.delete(id);
            }
        }

        async function archiveEnrichOpenProjectStatus(rows) {
            const list = Array.isArray(rows) ? rows : [];
            const items = list
                .map((row) => ({ entity_type: ARCHIVE_ENTITY_TYPE, entity_id: Number(row?.id || 0) }))
                .filter((item) => item.entity_id > 0);
            if (!items.length) return list;
            try {
                const payload = await archiveRequestJson('/api/v1/storage/openproject/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items }),
                });
                const resultItems = Array.isArray(payload?.items) ? payload.items : [];
                const map = new Map(
                    resultItems.map((item) => [Number(item?.entity_id || 0), item || {}])
                );
                return list.map((row) => {
                    const key = Number(row?.id || 0);
                    const resolved = map.get(key);
                    if (!resolved) return row;
                    return {
                        ...row,
                        openproject_sync_status: resolved.sync_status ?? row.openproject_sync_status,
                        openproject_work_package_id:
                            resolved.work_package_id ?? row.openproject_work_package_id ?? null,
                        openproject_attachment_id:
                            resolved.openproject_attachment_id ?? row.openproject_attachment_id ?? null,
                        openproject_last_synced_at:
                            resolved.last_synced_at ?? row.openproject_last_synced_at ?? null,
                    };
                });
            } catch (error) {
                console.error('Failed to fetch OpenProject status map for archive files', error);
                return list;
            }
        }

        async function archiveShowIntegrity(fileId, fileName) {
            const id = Number(fileId || 0);
            if (!id) return;
            try {
                const payload = await archiveRequestJson(`/api/v1/archive/files/${id}/integrity`);
                const lines = [
                    `File: ${String(fileName || '-')}`,
                    `SHA-256: ${String(payload?.sha256 || '-')}`,
                    `Validation: ${String(payload?.validation_status || '-')}`,
                    `Detected MIME: ${String(payload?.detected_mime || '-')}`,
                    `Mirror: ${String(payload?.mirror_status || '-')}`,
                    `OpenProject: ${String(payload?.openproject_sync_status || '-')}`,
                ];
                alert(lines.join('\n'));
            } catch (error) {
                alert(`Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª Ø§Ø·Ù„Ø§Ø¹Ø§Øª ÛŒÚ©Ù¾Ø§Ø±Ú†Ú¯ÛŒ ÙØ§ÛŒÙ„.\nØ¬Ø²Ø¦ÛŒØ§Øª: ${String(error?.message || '')}`);
            }
        }

        function archiveFileExtension(fileName = '') {
            const name = String(fileName || '').trim();
            const idx = name.lastIndexOf('.');
            if (idx < 0) return '';
            return name.substring(idx + 1).toLowerCase();
        }

        function archiveFormatFileSize(bytes = 0) {
            const size = Number(bytes || 0);
            if (!Number.isFinite(size) || size <= 0) return '-';
            if (size < 1024) return `${size} B`;
            if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
            if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
            return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
        }

        function archiveSetDropzoneState(kind, state = 'idle') {
            const zone = document.getElementById(kind === 'native' ? 'archiveNativeDropzone' : 'archivePdfDropzone');
            if (!zone) return;
            zone.classList.remove('is-dragover', 'is-invalid', 'is-valid');
            if (state === 'dragover') zone.classList.add('is-dragover');
            if (state === 'invalid') zone.classList.add('is-invalid');
            if (state === 'valid') zone.classList.add('is-valid');
        }

        function archiveSetValidationMessage(kind, message = '', level = 'info') {
            const el = document.getElementById(kind === 'native' ? 'archiveNativeValidation' : 'archivePdfValidation');
            if (!el) return;
            el.classList.remove('is-error', 'is-success', 'is-info');
            if (!message) {
                el.textContent = '';
                return;
            }
            const cls = level === 'error' ? 'is-error' : (level === 'success' ? 'is-success' : 'is-info');
            el.classList.add(cls);
            el.textContent = message;
        }

        function archiveValidateFileByKind(file, kind = 'pdf') {
            if (!file) {
                return { ok: false, message: 'ÙØ§ÛŒÙ„ÛŒ Ø§Ù†ØªØ®Ø§Ø¨ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.' };
            }
            const ext = archiveFileExtension(file.name);
            if (!ext) {
                return { ok: false, message: 'Ù¾Ø³ÙˆÙ†Ø¯ ÙØ§ÛŒÙ„ Ù‚Ø§Ø¨Ù„ ØªØ´Ø®ÛŒØµ Ù†ÛŒØ³Øª.' };
            }
            if (kind === 'pdf') {
                if (!ARCHIVE_OUTPUT_ALLOWED_EXTENSIONS.has(ext)) {
                    return { ok: false, message: 'ÙØ±Ù…Øª ÙØ§ÛŒÙ„ Ø®Ø±ÙˆØ¬ÛŒ Ø¨Ø§ÛŒØ¯ PDFØŒ ØªØµÙˆÛŒØ± ÛŒØ§ DWF/DWFX Ø¨Ø§Ø´Ø¯.' };
                }
                return { ok: true, message: 'ÙØ±Ù…Øª ÙØ§ÛŒÙ„ Ø®Ø±ÙˆØ¬ÛŒ Ù…Ø¹ØªØ¨Ø± Ø§Ø³Øª.' };
            }
            if (ARCHIVE_NATIVE_BLOCKED_EXTENSIONS.has(ext)) {
                return { ok: false, message: 'Ø§ÛŒÙ† Ù†ÙˆØ¹ ÙØ§ÛŒÙ„ Ø¨Ø±Ø§ÛŒ Native Ù…Ø¬Ø§Ø² Ù†ÛŒØ³Øª.' };
            }
            return { ok: true, message: 'ÙØ±Ù…Øª Native Ù…Ø¹ØªØ¨Ø± ØªØ´Ø®ÛŒØµ Ø¯Ø§Ø¯Ù‡ Ø´Ø¯.' };
        }

        function archiveAssignFileToInput(file, kind = 'pdf') {
            const input = document.getElementById(kind === 'native' ? 'archiveNativeFileInput' : 'archivePdfFileInput');
            if (!input || !file) return false;
            try {
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                return true;
            } catch (_) {
                return false;
            }
        }

        function archiveValidateSelectedFilesBeforeSubmit(pdfFile, nativeFile) {
            if (!pdfFile && !nativeFile) {
                return { ok: false, kind: 'pdf', message: 'حداقل یک فایل خروجی یا Native انتخاب کنید.' };
            }
            if (pdfFile) {
                const pdfValidation = archiveValidateFileByKind(pdfFile, 'pdf');
                if (!pdfValidation.ok) return { ...pdfValidation, kind: 'pdf' };
            }
            if (nativeFile) {
                const nativeValidation = archiveValidateFileByKind(nativeFile, 'native');
                if (!nativeValidation.ok) return { ...nativeValidation, kind: 'native' };
            }
            return { ok: true };
        }

        function archiveInitDropzones() {
            if (archiveDropzonesBound) return;
            archiveDropzonesBound = true;
            const dropzones = document.querySelectorAll('.archive-dropzone[data-kind]');
            dropzones.forEach((zone) => {
                const kind = zone.getAttribute('data-kind') === 'native' ? 'native' : 'pdf';
                const stop = (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                };
                zone.addEventListener('dragenter', (event) => {
                    stop(event);
                    archiveSetDropzoneState(kind, 'dragover');
                });
                zone.addEventListener('dragover', (event) => {
                    stop(event);
                    archiveSetDropzoneState(kind, 'dragover');
                });
                zone.addEventListener('dragleave', (event) => {
                    stop(event);
                    archiveSetDropzoneState(kind, 'idle');
                });
                zone.addEventListener('drop', (event) => {
                    stop(event);
                    archiveSetDropzoneState(kind, 'idle');
                    const file = event.dataTransfer?.files?.[0];
                    if (!file) return;
                    const check = archiveValidateFileByKind(file, kind);
                    if (!check.ok) {
                        archiveSetDropzoneState(kind, 'invalid');
                        archiveSetValidationMessage(kind, check.message, 'error');
                        return;
                    }
                    if (!archiveAssignFileToInput(file, kind)) {
                        archiveSetDropzoneState(kind, 'invalid');
                        archiveSetValidationMessage(kind, 'Ù…Ø±ÙˆØ±Ú¯Ø± Ø§Ù…Ú©Ø§Ù† Ø«Ø¨Øª ÙØ§ÛŒÙ„ Ú©Ø´ÛŒØ¯Ù‡â€ŒØ´Ø¯Ù‡ Ø±Ø§ Ù†Ø¯Ø§Ø¯. Ù„Ø·ÙØ§Ù‹ ÙØ§ÛŒÙ„ Ø±Ø§ Ø¯Ø³ØªÛŒ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯.', 'error');
                        return;
                    }
                    const input = document.getElementById(kind === 'native' ? 'archiveNativeFileInput' : 'archivePdfFileInput');
                    archiveOnFileSelect(input, kind);
                });
            });
        }

        const archiveViewEl = document.getElementById('view-archive');
        if (archiveViewEl && archiveViewEl.style.display !== 'none') {
            archiveLoadFilterCatalog();
            archiveLoadFiles();
        }

        async function archiveGetFormData(force = false) {
            if (!force && archiveFormDataCache) {
                return archiveFormDataCache;
            }
            if (!force && archiveFormDataPromise) {
                return archiveFormDataPromise;
            }
            archiveFormDataPromise = (async () => {
                const res = await window.fetchWithAuth('/api/v1/archive/form-data');
                const payload = await res.json();
                archiveFormDataCache = payload;
                return payload;
            })();
            try {
                return await archiveFormDataPromise;
            } finally {
                archiveFormDataPromise = null;
            }
        }

        async function loadFormData(force = false) {
            try {
                const data = await archiveGetFormData(force);
                allPackages = data.packages; 
                allBlocks = data.blocks;
                const fillSimple = (id, arr) => {
                    const el = document.getElementById(id);
                    if(!el) return;
                    el.innerHTML = '';
                    arr.forEach(val => { const op = document.createElement('option'); op.value = val; op.innerText = val; el.appendChild(op); });
                };
                const fillObject = (id, arr) => {
                    const el = document.getElementById(id);
                    if(!el) return;
                    el.innerHTML = '';
                    arr.forEach(item => { const op = document.createElement('option'); op.value = item.code; op.innerText = item.name ? `${item.code} - ${item.name}` : item.code; el.appendChild(op); });
                };
                fillObject('regProject', data.projects);
                fillObject('regDisc', data.disciplines);
                fillObject('regMdr', data.mdr_categories);
                fillObject('regPhase', data.phases);
                fillSimple('regLevel', data.levels);
                onProjectChange();
                onDisciplineChange();
            } catch(e) { console.error("Error loading form data", e); }
        }

        async function archiveLoadFilterCatalog() {
            try {
                const data = await archiveGetFormData();
                const projectSelect = document.getElementById('archiveProjectFilter');
                const disciplineSelect = document.getElementById('archiveDisciplineFilter');
                const prevProject = projectSelect?.value || '';
                const prevDiscipline = disciplineSelect?.value || '';

                if (projectSelect) {
                    projectSelect.innerHTML = '<option value="">All Projects</option>';
                    (data.projects || []).forEach((item) => {
                        const op = document.createElement('option');
                        op.value = item.code;
                        op.innerText = item.name ? `${item.code} - ${item.name}` : item.code;
                        projectSelect.appendChild(op);
                    });
                    if (prevProject) projectSelect.value = prevProject;
                }

                if (disciplineSelect) {
                    disciplineSelect.innerHTML = '<option value="">All Disciplines</option>';
                    (data.disciplines || []).forEach((item) => {
                        const op = document.createElement('option');
                        op.value = item.code;
                        op.innerText = item.name ? `${item.code} - ${item.name}` : item.code;
                        disciplineSelect.appendChild(op);
                    });
                    if (prevDiscipline) disciplineSelect.value = prevDiscipline;
                }
            } catch (error) {
                console.error('Error loading archive filter catalog', error);
            }
        }

        function onProjectChange() {
            const selectedProj = document.getElementById('regProject').value;
            const el = document.getElementById('regBlock');
            el.innerHTML = '';
            const filtered = allBlocks.filter(b => b.project_code === selectedProj);
            if(filtered.length === 0) { const op = document.createElement('option'); op.value = 'G'; op.innerText = 'G - General'; el.appendChild(op); } 
            else { filtered.forEach(b => { const op = document.createElement('option'); op.value = b.code; op.innerText = b.name ? `${b.code} - ${b.name}` : b.code; el.appendChild(op); }); }
            updateSerialAndPreview();
        }

        function onDisciplineChange() {
            const selectedDisc = document.getElementById('regDisc').value;
            const el = document.getElementById('regPkg');
            el.innerHTML = '';
            const filtered = allPackages.filter(p => p.discipline_code === selectedDisc);
            if (filtered.length === 0) { const op = document.createElement('option'); op.value = ""; op.innerText = "(Ù¾Ú©ÛŒØ¬ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯)"; op.disabled = true; op.selected = true; el.appendChild(op); } 
            else { filtered.forEach(p => { const op = document.createElement('option'); op.value = p.code; op.innerText = p.name ? `${p.code} - ${p.name}` : p.code; el.appendChild(op); }); }
            updateSerialAndPreview();
        }

        function archiveGetUnifiedSubject() {
            const single = String(document.getElementById('regSubject')?.value || '').trim();
            if (single) return single;
            const legacyP = String(document.getElementById('regSubjectP')?.value || '').trim();
            if (legacyP) return legacyP;
            return String(document.getElementById('regSubjectE')?.value || '').trim();
        }

        function archiveGetPackageNames(disciplineCode, packageCode) {
            const normalizedDiscipline = String(disciplineCode || '').trim();
            const normalizedPackage = String(packageCode || '').trim();
            const hit = allPackages.find((item) => (
                String(item?.discipline_code || '') === normalizedDiscipline &&
                String(item?.code || '') === normalizedPackage
            ));
            const fallback = normalizedPackage || '00';
            const nameE = String(hit?.name_e || hit?.name || fallback).trim() || fallback;
            const nameP = String(hit?.name_p || hit?.name_e || hit?.name || fallback).trim() || nameE;
            return { nameE, nameP };
        }

        function archiveBuildPreviewTitles() {
            const discipline = String(document.getElementById('regDisc')?.value || '').trim();
            const pkg = String(document.getElementById('regPkg')?.value || '').trim();
            const block = String(document.getElementById('regBlock')?.value || 'G').trim().toUpperCase() || 'G';
            const level = String(document.getElementById('regLevel')?.value || 'GEN').trim().toUpperCase() || 'GEN';
            const subject = archiveGetUnifiedSubject();
            if (!pkg || !block || !level) {
                return { titleE: '', titleP: '' };
            }

            const pkgNames = archiveGetPackageNames(discipline, pkg);
            const omitLocation = block === 'T' && level === 'GEN';
            const locationPart = `${block}${level}`;

            let titleE = pkgNames.nameE;
            if (!omitLocation) titleE = `${titleE}-${locationPart}`;
            if (subject) titleE = `${titleE} - ${subject}`;

            let titleP = omitLocation ? pkgNames.nameP : `${locationPart}-${pkgNames.nameP}`;
            if (subject) titleP = `${titleP}-${subject}`;

            return { titleE, titleP };
        }

        function archiveUpdateTitlePreview() {
            const titlePreviewEl = document.getElementById('fullDocTitlePPreview');
            if (!titlePreviewEl) return;
            const { titleP } = archiveBuildPreviewTitles();
            titlePreviewEl.value = titleP || '';
        }

        async function updateSerialAndPreview() {
            if (archiveSuspendAutoPreview) return;
            const project = document.getElementById('regProject').value;
            const mdr = document.getElementById('regMdr').value;
            const phase = document.getElementById('regPhase').value;
            const pkg = document.getElementById('regPkg').value;
            const disc = document.getElementById('regDisc').value;
            const block = document.getElementById('regBlock').value;
            const level = document.getElementById('regLevel').value;
            const subjectValue = archiveGetUnifiedSubject();
            const subjE = subjectValue;
            const subjP = subjectValue;
            archiveUpdateTitlePreview();
            if(!project || !mdr || !phase) {
                document.getElementById('fullDocNumber').value = '';
                document.getElementById('realDocId').value = '';
                archiveRefreshSubmitButtonState();
                return;
            }
            document.getElementById('fullDocNumber').value = "Calculating...";
            try {
                const params = new URLSearchParams({ project_code: project, mdr_code: mdr, phase: phase, pkg: pkg, discipline: disc, block: block, level: level, subject_e: subjE, subject_p: subjP });
                const res = await window.fetchWithAuth(`/api/v1/archive/next-serial?${params}`);
                const data = await res.json();
                const msgEl = document.getElementById('fullDocCheckMsg');
                const registerBtn = document.getElementById('fullRegisterDocBtn');
                if (data?.requires_subject) {
                    document.getElementById('regSerial').value = '';
                    document.getElementById('fullDocNumber').value = '';
                    document.getElementById('realDocId').value = '';
                    if (msgEl) {
                        msgEl.innerHTML = '<span style="color:#b45309">Ø¨Ø±Ø§ÛŒ Ø³Ø§Ø®Øª Ù…Ø¯Ø±Ú© Ø¬Ø¯ÛŒØ¯ Ø¨Ø§ÛŒØ¯ Subject ÙˆØ§Ø±Ø¯ Ø´ÙˆØ¯.</span>';
                    }
                    if (registerBtn) registerBtn.style.display = 'none';
                    archiveRefreshSubmitButtonState();
                    return;
                }
                document.getElementById('regSerial').value = data.serial;
                document.getElementById('fullDocNumber').value = data.full_doc;
                if (data && data.existing && Number(data.existing_document_id || 0) > 0) {
                    document.getElementById('realDocId').value = String(data.existing_document_id);
                } else {
                    document.getElementById('realDocId').value = '';
                }
                if (archiveFullPreviewTimer) clearTimeout(archiveFullPreviewTimer);
                archiveFullPreviewTimer = setTimeout(() => archiveCheckFullModeDocStatus(), 220);
            } catch(e) {
                document.getElementById('fullDocNumber').value = "Error";
                document.getElementById('realDocId').value = '';
                archiveRefreshSubmitButtonState();
            }
        }

        async function toggleRegistrationMode() {
            isFullMode = !isFullMode;
            const quick = document.getElementById('quickModeContainer');
            const full = document.getElementById('fullModeContainer');
            const btn = document.getElementById('toggleModeBtn');
            const prevInfo = document.getElementById('prevInfo');
            const fullMsg = document.getElementById('fullDocCheckMsg');
            const fullRegisterBtn = document.getElementById('fullRegisterDocBtn');
            document.getElementById('realDocId').value = '';
            if(isFullMode) {
                quick.style.display = 'none'; full.style.display = 'block';
                btn.innerHTML = '<span class="material-icons-round">speed</span> Ø¨Ø§Ø²Ú¯Ø´Øª Ø¨Ù‡ Ø­Ø§Ù„Øª Ø³Ø±ÛŒØ¹'; btn.classList.add('active'); prevInfo.style.display = 'none';
                await loadFormData(true);
                if (fullMsg) fullMsg.innerHTML = '';
                if (fullRegisterBtn) fullRegisterBtn.style.display = 'none';
                const prefilledFromQuick = await archiveTryPrefillFullModeFromQuickCode();
                if (prefilledFromQuick) {
                    if (archiveFullPreviewTimer) clearTimeout(archiveFullPreviewTimer);
                    archiveFullPreviewTimer = setTimeout(() => archiveCheckFullModeDocStatus(), 120);
                } else {
                    setTimeout(() => { updateSerialAndPreview(); }, 60);
                }
            } else {
                full.style.display = 'none'; quick.style.display = 'block';
                btn.innerHTML = '<span class="material-icons-round">tune</span> ØªØºÛŒÛŒØ± Ø¨Ù‡ Ø­Ø§Ù„Øª Ø«Ø¨Øª Ú©Ø§Ù…Ù„'; btn.classList.remove('active'); prevInfo.style.display = 'flex';
                if (fullMsg) fullMsg.innerHTML = '';
                if (fullRegisterBtn) fullRegisterBtn.style.display = 'none';
            }
            archiveRefreshSubmitButtonState();
        }

        function archiveRefreshSubmitButtonState() {
            const submitBtn = document.getElementById('btnArchiveSubmit');
            if (!submitBtn) return;
            const docId = Number(document.getElementById('realDocId')?.value || 0);
            const hasPdf = Boolean(document.getElementById('archivePdfFileInput')?.files?.[0]);
            const hasNative = Boolean(document.getElementById('archiveNativeFileInput')?.files?.[0]);
            if (isFullMode) {
                submitBtn.disabled = docId <= 0 || (!hasPdf && !hasNative);
                return;
            }
            submitBtn.disabled = docId <= 0 || (!hasPdf && !hasNative);
        }

        function archiveNormalizeDocCode(value) {
            return String(value || '').trim().toUpperCase();
        }

        function archiveSetSelectValue(selectId, targetValue, allowInject = false) {
            const select = document.getElementById(selectId);
            const normalizedTarget = archiveNormalizeDocCode(targetValue);
            if (!select || !normalizedTarget) return false;

            let option = Array.from(select.options || []).find((item) => archiveNormalizeDocCode(item.value) === normalizedTarget);
            if (!option && allowInject) {
                option = document.createElement('option');
                option.value = normalizedTarget;
                option.innerText = normalizedTarget;
                select.appendChild(option);
            }
            if (!option) return false;
            select.value = option.value;
            return true;
        }

        async function archiveTryPrefillFullModeFromQuickCode() {
            const quickCode = archiveNormalizeDocCode(document.getElementById('smartDocCode')?.value || '');
            if (quickCode.length < 5) return false;

            try {
                const res = await window.fetchWithAuth(`/api/v1/archive/check-status?doc_code=${encodeURIComponent(quickCode)}`);
                const data = await res.json();
                const parsed = (data && typeof data.parsed === 'object' && data.parsed) ? data.parsed : null;
                if (!parsed) return false;

                archiveSuspendAutoPreview = true;

                archiveSetSelectValue('regProject', parsed.project_code);
                onProjectChange();

                archiveSetSelectValue('regMdr', parsed.mdr_code);
                archiveSetSelectValue('regPhase', parsed.phase_code);
                archiveSetSelectValue('regDisc', parsed.discipline_code);
                onDisciplineChange();

                archiveSetSelectValue('regPkg', parsed.package_code, true);
                archiveSetSelectValue('regBlock', parsed.block, true);
                archiveSetSelectValue('regLevel', parsed.level_code, true);

                if (parsed.serial) {
                    document.getElementById('regSerial').value = archiveNormalizeDocCode(parsed.serial);
                }
                document.getElementById('fullDocNumber').value = quickCode;
                if (data.exists && Number(data.document_id || 0) > 0) {
                    document.getElementById('realDocId').value = String(data.document_id);
                } else {
                    document.getElementById('realDocId').value = '';
                }
                return true;
            } catch (error) {
                return false;
            } finally {
                archiveSuspendAutoPreview = false;
            }
        }

        async function archiveLoadQuickDocSuggestions(term) {
            const q = archiveNormalizeDocCode(term);
            const list = document.getElementById('archiveDocCodeSuggestions');
            if (!list) return;
            if (q.length < 2) {
                list.innerHTML = '';
                return;
            }
            try {
                const params = new URLSearchParams({ q, limit: '20' });
                const res = await window.fetchWithAuth(`/api/v1/archive/doc-suggestions?${params.toString()}`);
                const data = await res.json();
                const items = Array.isArray(data?.items) ? data.items : [];
                list.innerHTML = items
                    .map((item) => `<option value="${archiveEsc(item.doc_number || '')}">${archiveEsc(item.title_e || item.title_p || '')}</option>`)
                    .join('');
            } catch (e) {
                list.innerHTML = '';
            }
        }

        function archiveOnDocCodeInput() {
            const input = document.getElementById('smartDocCode');
            const code = archiveNormalizeDocCode(input?.value || '');
            if (input) input.value = code;
            const msgEl = document.getElementById('docStatusMsg');
            document.getElementById('realDocId').value = '';
            if (code.length < 5) {
                if (msgEl) msgEl.innerHTML = '';
                archiveRefreshSubmitButtonState();
                if (archiveDocSuggestTimer) clearTimeout(archiveDocSuggestTimer);
                archiveLoadQuickDocSuggestions(code);
                return;
            }
            archiveRefreshSubmitButtonState();
            clearTimeout(window.archiveDocCodeTimer);
            window.archiveDocCodeTimer = setTimeout(() => {
                checkDocStatus();
            }, 350);
            if (archiveDocSuggestTimer) clearTimeout(archiveDocSuggestTimer);
            archiveDocSuggestTimer = setTimeout(() => {
                archiveLoadQuickDocSuggestions(code);
            }, 180);
        }

        function archiveHandleDocCodeKey(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                checkDocStatus();
            }
        }

        function archiveEsc(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function archiveFormatCodeName(code, name) {
            const cleanCode = String(code || '').trim();
            const cleanName = String(name || '').trim();
            if (cleanCode && cleanName) return `${archiveEsc(cleanCode)} - ${archiveEsc(cleanName)}`;
            if (cleanCode) return archiveEsc(cleanCode);
            if (cleanName) return archiveEsc(cleanName);
            return '-';
        }

        function archiveRenderSummary(summary = {}) {
            const totalEl = document.getElementById('archiveSummaryTotal');
            const withFileEl = document.getElementById('archiveSummaryWithFile');
            const mdrOnlyEl = document.getElementById('archiveSummaryMdrOnly');
            if (totalEl) totalEl.textContent = String(Number(summary?.total_documents || 0));
            if (withFileEl) withFileEl.textContent = String(Number(summary?.with_file || 0));
            if (mdrOnlyEl) mdrOnlyEl.textContent = String(Number(summary?.mdr_only || 0));
        }

        function archiveCloseRowMenus() {
            document.querySelectorAll('[data-archive-row-menu].is-open').forEach((menuEl) => {
                menuEl.classList.remove('is-open');
                const trigger = menuEl.querySelector('[data-archive-action="toggle-row-menu"]');
                if (trigger) trigger.setAttribute('aria-expanded', 'false');
            });
        }

        function archiveToggleRowMenu(triggerEl) {
            const menuEl = triggerEl?.closest?.('[data-archive-row-menu]');
            if (!menuEl) return;
            const shouldOpen = !menuEl.classList.contains('is-open');
            archiveCloseRowMenus();
            if (shouldOpen) {
                menuEl.classList.add('is-open');
                triggerEl.setAttribute('aria-expanded', 'true');
            }
        }

        async function archiveLoadFiles(searchValue = null) {
            const tbody = document.getElementById('archiveTableBody');
            const loader = document.getElementById('archiveLoader');
            const empty = document.getElementById('archiveEmpty');
            const searchInput = document.getElementById('archiveSearchInput');
            const projectFilter = document.getElementById('archiveProjectFilter');
            const disciplineFilter = document.getElementById('archiveDisciplineFilter');
            const statusFilter = document.getElementById('archiveStatusFilter');
            const filePresenceFilter = document.getElementById('archiveFilePresenceFilter');
            const dateFromFilter = document.getElementById('archiveDateFromFilter');
            const dateToFilter = document.getElementById('archiveDateToFilter');
            tbody.innerHTML=''; loader.style.display='block'; empty.style.display='none';
            try {
                if (projectFilter && projectFilter.options.length <= 1) {
                    await archiveLoadFilterCatalog();
                }
                const search = String(searchValue ?? searchInput?.value ?? '').trim();
                const params = new URLSearchParams();
                if (search) params.set('search', search);
                if (projectFilter?.value) params.set('project_code', projectFilter.value);
                if (disciplineFilter?.value) params.set('discipline_code', disciplineFilter.value);
                if (statusFilter?.value) params.set('status', statusFilter.value);
                if (filePresenceFilter?.value) params.set('file_presence', filePresenceFilter.value);
                if (dateFromFilter?.value) params.set('date_from', dateFromFilter.value);
                if (dateToFilter?.value) params.set('date_to', dateToFilter.value);
                const siteContext = await archiveLoadSiteContext(projectFilter?.value || '', true);
                if (siteContext?.active && siteContext?.siteCode) {
                    params.set('site_code', siteContext.siteCode);
                }
                const url = `/api/v1/archive/list${params.toString() ? `?${params.toString()}` : ''}`;
                await archiveLoadPinManifest();
                const data = await archiveRequestJson(url);
                archiveRenderSummary(data?.summary || {});
                let rows = Array.isArray(data?.data) ? data.data : [];
                rows = await archiveEnrichOpenProjectStatus(rows);
                const effectiveRole = String(
                    window.authManager?.user?.effective_role || window.authManager?.user?.role || ''
                ).trim().toLowerCase();
                const hasCapability = (permissionKey, roleFallback = []) => {
                    if (typeof window.hasCapability === 'function') {
                        return Boolean(window.hasCapability(permissionKey));
                    }
                    return roleFallback.includes(effectiveRole);
                };
                const canEditDocument = hasCapability('documents:update', ['admin', 'manager', 'dcc', 'user']);
                const canSendTransmittal = hasCapability('transmittal:create', ['admin', 'manager', 'dcc', 'user']);
                const canDeleteDocument = hasCapability('documents:delete', ['admin', 'manager', 'dcc']);

                if (rows.length > 0) {
                    tbody.innerHTML = rows.map((f, i) => {
                        const fileId = Number(f.id || 0);
                        const isMdrOnly = Boolean(f.is_mdr_only) || !Boolean(f.has_uploaded_file);
                        const sizeText = archiveFormatFileSize(f.size);
                        const uploadedAt = formatShamsiDate(f.uploaded_at);
                        const pdfId = Number(f.pdf_file_id || 0);
                        const nativeId = Number(f.native_file_id || 0);
                        const hasNative = !isMdrOnly && nativeId > 0;
                        const hasPdf = !isMdrOnly && pdfId > 0;
                        const isPinned = archivePinnedSet.has(fileId);
                        const pinLabel = isMdrOnly
                            ? '\u0628\u0631\u0627\u06cc \u0631\u062f\u06cc\u0641\u200c\u0647\u0627\u06cc \u0628\u062f\u0648\u0646 \u0641\u0627\u06cc\u0644\u060c \u0647\u0645\u06af\u0627\u0645\u200c\u0633\u0627\u0632\u06cc \u062f\u0633\u06a9\u062a\u0627\u067e \u0641\u0639\u0627\u0644 \u0646\u06cc\u0633\u062a'
                            : isPinned
                            ? '\u0644\u063a\u0648 \u0647\u0645\u06af\u0627\u0645\u200c\u0633\u0627\u0632\u06cc \u0628\u0627 \u062f\u0633\u06a9\u062a\u0627\u067e'
                            : '\u0647\u0645\u06af\u0627\u0645\u200c\u0633\u0627\u0632\u06cc \u0628\u0627 \u062f\u0633\u06a9\u062a\u0627\u067e';
                        const pinClass = isMdrOnly
                            ? 'archive-pin-btn is-unpinned'
                            : isPinned
                            ? 'archive-pin-btn is-pinned'
                            : 'archive-pin-btn is-unpinned';
                        const projectText = archiveFormatCodeName(f.project_code, f.project_name);
                        const disciplineText = archiveFormatCodeName(f.discipline_code, f.discipline_name);
                        const packageText = archiveFormatCodeName(f.package_code, f.package_name);
                        const titleP = archiveEsc(f.doc_title_p || '-');
                        const titleE = archiveEsc(f.doc_title_e || '-');
                        const pdfTooltip = archiveEsc(
                            isMdrOnly
                                ? (f.row_message || 'This document exists in MDR but has no uploaded file yet.')
                                : (f.pdf_file_name || f.name || '-')
                        );
                        const nativeTooltip = archiveEsc(f.native_file_name || '-');
                        const pdfRelativePath = String(f.pdf_relative_path || f.site_relative_path || '').trim();
                        const nativeRelativePath = String(f.native_relative_path || '').trim();
                        const hasLocalContext = Boolean(archiveSiteContext?.active && archiveSiteContext?.localRootPath);
                        const localMenuItem = !isMdrOnly && hasLocalContext && pdfRelativePath
                            ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="open-local" data-site-relative-path="${archiveEsc(encodeURIComponent(pdfRelativePath))}" data-file-name="${archiveEsc(f.pdf_file_name || f.name || '')}">
                                                <span class="material-icons-round">folder_open</span>
                                                Open Local
                                            </button>
                            `
                            : '';
                        const securityIcons = isMdrOnly
                            ? `<span class="file-badge" style="background:#ecfccb;color:#3f6212;">MDR</span>`
                            : archiveBuildSecurityIcons(f);
                        const statusMarkup = isMdrOnly
                            ? `<span class="file-badge" style="background:#dbeafe;color:#1d4ed8;">ثبت‌شده در MDR</span>`
                            : `<span class="file-badge" style="background:#fef3c7;color:#92400e;">${archiveEsc(f.status)}</span>`;
                        const filesMarkup = isMdrOnly
                            ? `
                                    <div class="archive-files-group archive-files-group--empty">
                                        <span class="file-badge" style="background:#eef2ff;color:#3730a3;">بدون فایل</span>
                                        <button class="btn-archive-icon archive-mdr-upload-btn" type="button" data-archive-action="upload-for-document" data-document-id="${Number(f.document_id || 0)}" data-doc-number="${archiveEsc(f.doc_number || '')}">
                                            <span class="material-icons-round" style="font-size:18px;">cloud_upload</span>
                                        </button>
                                        <span class="archive-mdr-note">${archiveEsc(f.row_message || 'این مدرک در MDR ثبت شده است.')}</span>
                                    </div>
                            `
                            : `
                                    <div class="archive-files-group">
                                        <button class="btn-archive-icon archive-download-btn is-pdf" title="${pdfTooltip}" ${hasPdf ? '' : 'disabled'} data-archive-action="download-kind" data-kind="pdf" data-pdf-id="${pdfId}" data-native-id="${nativeId}" data-site-relative-path="${archiveEsc(encodeURIComponent(pdfRelativePath))}" data-file-name="${archiveEsc(f.pdf_file_name || f.name || '')}">
                                            <span class="material-icons-round" style="font-size:18px;">picture_as_pdf</span>
                                        </button>
                                        <button class="btn-archive-icon archive-download-btn is-native" title="${nativeTooltip}" ${hasNative ? '' : 'disabled'} data-archive-action="download-kind" data-kind="native" data-pdf-id="${pdfId}" data-native-id="${nativeId}" data-site-relative-path="${archiveEsc(encodeURIComponent(nativeRelativePath))}" data-file-name="${archiveEsc(f.native_file_name || '')}">
                                            <span class="material-icons-round" style="font-size:18px;">description</span>
                                        </button>
                                    </div>
                            `;
                        const downloadLatestMenuItem = !isMdrOnly
                            ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="download-latest" data-pdf-id="${pdfId}" data-native-id="${nativeId}" data-site-relative-path="${archiveEsc(encodeURIComponent(pdfRelativePath || nativeRelativePath || ''))}" data-file-name="${archiveEsc(f.pdf_file_name || f.native_file_name || f.name || '')}">
                                                <span class="material-icons-round">download</span>
                                                دانلود
                                            </button>
                            `
                            : '';
                        const sendTransmittalMenuItem = !isMdrOnly && canSendTransmittal
                            ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="send-transmittal" data-doc-number="${archiveEsc(f.doc_number)}" data-project-code="${archiveEsc(f.project_code || '')}" data-discipline-code="${archiveEsc(f.discipline_code || '')}" data-revision="${archiveEsc(f.revision || '00')}">
                                                <span class="material-icons-round">send</span>
                                                ارسال ترنسمیتال
                                            </button>`
                            : '';
                        const integrityMenuItem = !isMdrOnly
                            ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="show-integrity" data-file-id="${fileId}" data-file-name="${archiveEsc(f.name)}">
                                                <span class="material-icons-round">verified</span>
                                                Integrity
                                            </button>
                            `
                            : '';
                        const uploadForDocumentMenuItem = isMdrOnly
                            ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="upload-for-document" data-document-id="${Number(f.document_id || 0)}" data-doc-number="${archiveEsc(f.doc_number || '')}">
                                                <span class="material-icons-round">cloud_upload</span>
                                                آپلود فایل برای این سند
                                            </button>
                            `
                            : '';

                        const rowClass = isMdrOnly ? 'archive-row--mdr-only' : '';

                        return `
                            <tr class="${rowClass}">
                                <td style="color:#9ca3af;">${i+1}</td>
                                <td style="text-align:center;">
                                    <button class="${pinClass}" type="button" title="${pinLabel}" ${isMdrOnly ? 'disabled' : ''} data-archive-action="toggle-pin" data-file-id="${fileId}" data-pinned="${isPinned ? '1' : '0'}">
                                        <span class="material-icons-round">push_pin</span>
                                    </button>
                                </td>
                                <td class="archive-doc-number">${archiveEsc(f.doc_number)}</td>
                                <td>${titleP}</td>
                                <td class="archive-title-e">${titleE}</td>
                                <td>${projectText}</td>
                                <td>${disciplineText}</td>
                                <td>${packageText}</td>
                                <td><span class="archive-revision-badge">${archiveEsc(f.revision)}</span></td>
                                <td>${statusMarkup}</td>
                                <td>${sizeText}</td>
                                <td>${uploadedAt}</td>
                                <td style="text-align:center;">${securityIcons}</td>
                                <td style="text-align:center;">${filesMarkup}</td>
                                <td class="archive-row-actions-cell">
                                    <div class="archive-row-menu" data-archive-row-menu>
                                        <button class="btn-archive-icon archive-row-menu-trigger" type="button" title="Actions" data-archive-action="toggle-row-menu" aria-expanded="false">
                                            <span class="material-icons-round" style="font-size:18px;">more_vert</span>
                                        </button>
                                        <div class="archive-row-menu-dropdown">
                                            <button class="archive-row-menu-item" type="button" data-archive-action="open-detail" data-document-id="${Number(f.document_id || 0)}">
                                                <span class="material-icons-round">visibility</span>
                                                مشاهده جزییات
                                            </button>
                                            ${canEditDocument ? `
                                            <button class="archive-row-menu-item" type="button" data-archive-action="edit-detail" data-document-id="${Number(f.document_id || 0)}">
                                                <span class="material-icons-round">edit</span>
                                                ویرایش
                                            </button>` : ''}
                                            ${downloadLatestMenuItem}
                                            ${sendTransmittalMenuItem}
                                            ${uploadForDocumentMenuItem}
                                            <button class="archive-row-menu-item" type="button" data-archive-action="copy-doc" data-doc-number="${archiveEsc(f.doc_number)}">
                                                <span class="material-icons-round">content_copy</span>
                                                Copy Doc Number
                                            </button>
                                            ${localMenuItem}
                                            <button class="archive-row-menu-item" type="button" data-archive-action="open-history" data-document-id="${Number(f.document_id || 0)}" data-doc-number="${archiveEsc(f.doc_number)}">
                                                <span class="material-icons-round">history</span>
                                                Revision History
                                            </button>
                                            ${integrityMenuItem}
                                            ${canDeleteDocument ? `
                                            <div class="divider"></div>
                                            <button class="archive-row-menu-item text-danger" type="button" data-archive-action="delete-document" data-document-id="${Number(f.document_id || 0)}">
                                                <span class="material-icons-round">delete</span>
                                                حذف
                                            </button>` : ''}
                                        </div>
                                    </div>
                                </td>
                            </tr>`;
                    }).join('');
                } else {
                    archiveRenderSummary(data?.summary || {});
                    empty.style.display='block';
                }
            } catch(e) {
                console.error(e);
                archiveRenderSummary({});
            } finally {
                loader.style.display='none';
            }
        }

        function archiveApplyFilters() {
            archiveLoadFiles();
        }

        function archiveResetFilters() {
            const projectFilter = document.getElementById('archiveProjectFilter');
            const disciplineFilter = document.getElementById('archiveDisciplineFilter');
            const statusFilter = document.getElementById('archiveStatusFilter');
            const filePresenceFilter = document.getElementById('archiveFilePresenceFilter');
            const dateFromFilter = document.getElementById('archiveDateFromFilter');
            const dateToFilter = document.getElementById('archiveDateToFilter');
            if (projectFilter) projectFilter.value = '';
            if (disciplineFilter) disciplineFilter.value = '';
            if (statusFilter) statusFilter.value = '';
            if (filePresenceFilter) filePresenceFilter.value = '';
            if (dateFromFilter) dateFromFilter.value = '';
            if (dateToFilter) dateToFilter.value = '';
            archiveLoadFiles();
        }

        async function checkDocStatus() {
            const input = document.getElementById('smartDocCode');
            const code = archiveNormalizeDocCode(input?.value || '');
            if (input) input.value = code;
            const msgEl = document.getElementById('docStatusMsg');
            if(code.length < 5) {
                document.getElementById('realDocId').value = '';
                if (msgEl) msgEl.innerHTML = '';
                archiveRefreshSubmitButtonState();
                return;
            }
            msgEl.innerHTML = `<span style="color:blue">Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø±Ø±Ø³ÛŒ...</span>`;
            try {
                const res = await window.fetchWithAuth(`/api/v1/archive/check-status?doc_code=${encodeURIComponent(code)}`);
                const data = await res.json();
                if(data.exists) {
                    if (input && data.doc_number) input.value = String(data.doc_number || '');
                    const existingDoc = archiveNormalizeDocCode(data.doc_number || code);
                    msgEl.innerHTML = `<span style="color:green">Ø§ÛŒÙ† Ù…Ø¯Ø±Ú© Ù‚Ø¨Ù„Ø§Ù‹ Ø«Ø¨Øª Ø´Ø¯Ù‡: <b>${archiveEsc(existingDoc)}</b></span>`;
                    document.getElementById('realDocId').value = data.document_id;
                    document.getElementById('newRevInput').value = data.next_revision_suggestion;
                    document.getElementById('prevRev').innerText = data.last_revision;
                    document.getElementById('prevStatus').innerText = data.last_status;
                } else {
                    document.getElementById('realDocId').value = '';
                    document.getElementById('newRevInput').value = '00';
                    document.getElementById('prevRev').innerText = '-';
                    document.getElementById('prevStatus').innerText = '-';
                    msgEl.innerHTML = `<span style="color:#b45309">Ø§ÛŒÙ† Ø´Ù…Ø§Ø±Ù‡ Ø³Ù†Ø¯ Ø¯Ø± mdr_documents Ù…ÙˆØ¬ÙˆØ¯ Ù†ÛŒØ³Øª. Ø¯Ø± Ø­Ø§Ù„Øª Ø³Ø±ÛŒØ¹ Ø§Ù…Ú©Ø§Ù† Ø³Ø§Ø®Øª Ø³Ù†Ø¯ ÙˆØ¬ÙˆØ¯ Ù†Ø¯Ø§Ø±Ø¯.</span>`;
                }
            } catch(e) {
                document.getElementById('realDocId').value = '';
                msgEl.innerHTML = "Ø®Ø·Ø§";
            } finally {
                archiveRefreshSubmitButtonState();
            }
        }

        async function archiveCheckFullModeDocStatus() {
            if (!isFullMode) return;
            const docCode = archiveNormalizeDocCode(document.getElementById('fullDocNumber')?.value || '');
            const msgEl = document.getElementById('fullDocCheckMsg');
            const registerBtn = document.getElementById('fullRegisterDocBtn');
            if (!docCode || docCode === 'CALCULATING...' || docCode === 'ERROR') {
                document.getElementById('realDocId').value = '';
                if (msgEl) msgEl.innerHTML = '';
                if (registerBtn) registerBtn.style.display = 'none';
                archiveRefreshSubmitButtonState();
                return;
            }
            if (msgEl) msgEl.innerHTML = `<span style="color:#2563eb">Ø¨Ø±Ø±Ø³ÛŒ ÙˆØ¬ÙˆØ¯ Ø³Ù†Ø¯...</span>`;
            try {
                const res = await window.fetchWithAuth(`/api/v1/archive/check-status?doc_code=${encodeURIComponent(docCode)}`);
                const data = await res.json();
                if(data.exists) {
                    const existingDoc = archiveNormalizeDocCode(data.doc_number || docCode);
                    if (msgEl) msgEl.innerHTML = `<span style="color:green">Ø§ÛŒÙ† Ù…Ø¯Ø±Ú© Ù‚Ø¨Ù„Ø§Ù‹ Ø«Ø¨Øª Ø´Ø¯Ù‡: <b>${archiveEsc(existingDoc)}</b></span>`;
                    document.getElementById('realDocId').value = data.document_id;
                    document.getElementById('newRevInput').value = data.next_revision_suggestion || '00';
                    document.getElementById('prevRev').innerText = data.last_revision || '-';
                    document.getElementById('prevStatus').innerText = data.last_status || '-';
                    if (registerBtn) registerBtn.style.display = 'none';
                } else {
                    document.getElementById('realDocId').value = '';
                    document.getElementById('newRevInput').value = '00';
                    document.getElementById('prevRev').innerText = '-';
                    document.getElementById('prevStatus').innerText = '-';
                    if (msgEl) msgEl.innerHTML = `<span style="color:#b45309">Ø§ÛŒÙ† Ø´Ù…Ø§Ø±Ù‡ Ø³Ù†Ø¯ Ù‡Ù†ÙˆØ² Ø¯Ø± mdr_documents Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª. Ø§Ø¨ØªØ¯Ø§ Ø¯Ú©Ù…Ù‡ Â«Ø«Ø¨Øª Ù…Ø¯Ø±Ú©Â» Ø±Ø§ Ø¨Ø²Ù†ÛŒØ¯.</span>`;
                    if (registerBtn) registerBtn.style.display = 'inline-flex';
                }
            } catch(e) {
                document.getElementById('realDocId').value = '';
                if (msgEl) msgEl.innerHTML = '<span style="color:#dc2626">Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø±Ø±Ø³ÛŒ Ø´Ù…Ø§Ø±Ù‡ Ø³Ù†Ø¯</span>';
                if (registerBtn) registerBtn.style.display = 'none';
            } finally {
                archiveRefreshSubmitButtonState();
            }
        }

        async function archiveRegisterPreviewDocument() {
            if (!isFullMode) return;
            const btn = document.getElementById('fullRegisterDocBtn');
            const msgEl = document.getElementById('fullDocCheckMsg');
            const doc_number = archiveNormalizeDocCode(document.getElementById('fullDocNumber')?.value || '');
            if (!doc_number) return;
            const subjectValue = archiveGetUnifiedSubject();
            // Subject can be empty; backend enforces subjectless scope rule (serial 01).

            const payload = new FormData();
            payload.set('doc_number', doc_number);
            payload.set('project_code', document.getElementById('regProject')?.value || '');
            payload.set('mdr_code', document.getElementById('regMdr')?.value || '');
            payload.set('phase', document.getElementById('regPhase')?.value || '');
            payload.set('discipline', document.getElementById('regDisc')?.value || '');
            payload.set('package', document.getElementById('regPkg')?.value || '');
            payload.set('block', document.getElementById('regBlock')?.value || '');
            payload.set('level', document.getElementById('regLevel')?.value || '');
            payload.set('subject_e', subjectValue);
            payload.set('subject_p', subjectValue);

            if (btn) btn.disabled = true;
            if (msgEl) msgEl.innerHTML = '<span style="color:#2563eb">Ø¯Ø± Ø­Ø§Ù„ Ø«Ø¨Øª Ù…Ø¯Ø±Ú©...</span>';
            try {
                const res = await window.fetchWithAuth('/api/v1/archive/register-document', { method: 'POST', body: payload });
                const data = await res.json();
                if (!data?.ok) {
                    throw new Error(data?.detail || data?.message || 'Ø®Ø·Ø§ Ø¯Ø± Ø«Ø¨Øª Ù…Ø¯Ø±Ú©');
                }
                document.getElementById('realDocId').value = data.document_id;
                if (data.doc_number) {
                    document.getElementById('fullDocNumber').value = data.doc_number;
                }
                document.getElementById('newRevInput').value = data.next_revision_suggestion || '00';
                document.getElementById('prevRev').innerText = data.last_revision || '-';
                document.getElementById('prevStatus').innerText = data.last_status || 'Registered';
                if (msgEl) {
                    if (data.created) {
                        msgEl.innerHTML = '<span style="color:green">Ù…Ø¯Ø±Ú© Ø¬Ø¯ÛŒØ¯ Ø«Ø¨Øª Ø´Ø¯.</span>';
                    } else {
                        const existingDoc = archiveNormalizeDocCode(data.doc_number || doc_number);
                        msgEl.innerHTML = `<span style="color:green">Ø§ÛŒÙ† Ù…Ø¯Ø±Ú© Ù‚Ø¨Ù„Ø§Ù‹ Ø«Ø¨Øª Ø´Ø¯Ù‡: <b>${archiveEsc(existingDoc)}</b></span>`;
                    }
                }
                if (btn) btn.style.display = 'none';
            } catch (e) {
                if (msgEl) msgEl.innerHTML = `<span style="color:#dc2626">${archiveEsc(e?.message || 'Ø®Ø·Ø§ Ø¯Ø± Ø«Ø¨Øª Ù…Ø¯Ø±Ú©')}</span>`;
            } finally {
                if (btn) btn.disabled = false;
                archiveRefreshSubmitButtonState();
            }
        }

        async function archiveHandleUpload(e) {
            e.preventDefault();
            const form = e.target;
            const btn = document.getElementById('btnArchiveSubmit');
            const docId = Number(document.getElementById('realDocId').value || 0);
            const pdfFile = document.getElementById('archivePdfFileInput')?.files?.[0];
            const nativeFile = document.getElementById('archiveNativeFileInput')?.files?.[0];
            const revision = String(document.getElementById('newRevInput')?.value || '00').trim() || '00';
            const status = String(form.querySelector('select[name="status"]')?.value || 'IFA').trim() || 'IFA';
            const submitText = "ØªØ§ÛŒÛŒØ¯ Ùˆ Ø¢Ù¾Ù„ÙˆØ¯ Ù†Ù‡Ø§ÛŒÛŒ";

            if (!pdfFile && !nativeFile) {
                archiveSetDropzoneState('pdf', 'invalid');
                archiveSetValidationMessage('pdf', 'حداقل یک فایل خروجی یا Native انتخاب کنید.', 'error');
                return;
            }

            const validation = archiveValidateSelectedFilesBeforeSubmit(pdfFile, nativeFile);
            if (!validation.ok) {
                const targetKind = validation.kind || 'pdf';
                archiveSetDropzoneState(targetKind, 'invalid');
                archiveSetValidationMessage(targetKind, validation.message || 'ÙØ§ÛŒÙ„ Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡ Ù…Ø¹ØªØ¨Ø± Ù†ÛŒØ³Øª.', 'error');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = "Ø¯Ø±Ø­Ø§Ù„ Ø§Ø±Ø³Ø§Ù„...";

            try {
                if (!docId) {
                    if (isFullMode) {
                        alert("Ù…Ø¯Ø±Ú© Ù‡Ù†ÙˆØ² Ø«Ø¨Øª Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª. Ø§Ø¨ØªØ¯Ø§ Ø¯Ú©Ù…Ù‡ Â«Ø«Ø¨Øª Ù…Ø¯Ø±Ú©Â» Ø±Ø§ Ø¨Ø²Ù†ÛŒØ¯.");
                    } else {
                        alert("Ø´Ù…Ø§Ø±Ù‡ Ø³Ù†Ø¯ Ù…Ø¹ØªØ¨Ø± Ø§Ø² Ù„ÛŒØ³Øª Ù…Ø¯Ø§Ø±Ú© Ù…ÙˆØ¬ÙˆØ¯ Ø§Ù†ØªØ®Ø§Ø¨ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª.");
                    }
                    return;
                }

                if (pdfFile && nativeFile) {
                    const dualData = new FormData();
                    dualData.set('document_id', String(docId));
                    dualData.set('revision', revision);
                    dualData.set('status', status);
                    dualData.set('pdf_file', pdfFile);
                    dualData.set('native_file', nativeFile);
                    await archiveRequestJson('/api/v1/archive/upload-dual', { method: 'POST', body: dualData });
                } else {
                    const uploadFile = pdfFile || nativeFile;
                    const fileKind = pdfFile ? 'pdf' : 'native';
                    const singleData = new FormData();
                    singleData.set('document_id', String(docId));
                    singleData.set('revision', revision);
                    singleData.set('status', status);
                    singleData.set('file', uploadFile);
                    singleData.set('file_kind', fileKind);
                    await archiveRequestJson('/api/v1/archive/upload', { method: 'POST', body: singleData });
                }

                alert("Ø¨Ø§ Ù…ÙˆÙÙ‚ÛŒØª Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯");
                archiveCloseModal();
                archiveLoadFiles();
            } catch (err) {
                console.error(err);
                alert(archiveFriendlyUploadMessage(err));
            } finally {
                btn.disabled = false;
                btn.innerHTML = submitText;
            }
        }

        async function archiveDownloadFile(fileId, options = {}) {
            const relativePath = String(options?.relativePath || '').trim();
            const preferLocal = options?.preferLocal !== false;
            if (preferLocal && archiveSiteContext?.active && relativePath) {
                const localOpened = await archiveTryOpenLocal(relativePath, options?.fileName || '');
                if (localOpened) return;
            }
            try {
                const response = await window.fetchWithAuth(`/api/v1/archive/download/${fileId}`);
                if (!response || !response.ok) {
                    alert('Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª ÙØ§ÛŒÙ„');
                    return;
                }
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                let filename = `archive-${fileId}`;
                const contentDisposition = response.headers.get('Content-Disposition') || response.headers.get('content-disposition') || '';
                const match = contentDisposition.match(/filename\*?=(?:UTF-8''|\"?)([^\";]+)/i);
                if (match && match[1]) {
                    try {
                        filename = decodeURIComponent(match[1].replace(/\"/g, '').trim());
                    } catch (_) {
                        filename = match[1].replace(/\"/g, '').trim();
                    }
                }
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } catch (e) {
                console.error(e);
                alert('Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛŒØ§ÙØª ÙØ§ÛŒÙ„');
            }
        }

        async function archiveDownloadByKind(pdfFileId, nativeFileId, kind, relativePath = '', fileName = '') {
            const targetId = kind === 'native' ? Number(nativeFileId || 0) : Number(pdfFileId || 0);
            if (!targetId) {
                alert(kind === 'native' ? 'Native file not found.' : 'PDF file not found.');
                return;
            }
            const canTryLocal = kind === 'pdf' ? true : Boolean(relativePath);
            await archiveDownloadFile(targetId, {
                relativePath: canTryLocal ? relativePath : '',
                fileName,
                preferLocal: true,
            });
        }

        function archiveCopyDocNumber(docNumber) {
            const value = String(docNumber || '').trim();
            if (!value) return;
            if (typeof copyToClipboard === 'function') {
                copyToClipboard(value);
                return;
            }
            navigator.clipboard.writeText(value).then(() => {
                alert('Copied');
            }).catch(() => {
                alert('Copy failed');
            });
        }

        async function archiveNavigateToDocumentDetail(documentId, editMode = false) {
            const id = Number(documentId || 0);
            if (!id) {
                alert('Document id not found.');
                return;
            }
            if (typeof window.navigateToDocumentDetail === 'function') {
                await window.navigateToDocumentDetail(id, { editMode: Boolean(editMode) });
                return;
            }
            if (typeof window.navigateTo === 'function') {
                if (typeof window.setPendingDocumentDetailId === 'function') {
                    window.setPendingDocumentDetailId(id, { editMode: Boolean(editMode) });
                }
                await window.navigateTo('view-document-detail');
            }
        }

        async function archiveDeleteDocument(documentId) {
            const id = Number(documentId || 0);
            if (!id) {
                alert('Document id not found.');
                return;
            }
            const confirmed = window.confirm('این سند به صورت Soft Delete حذف شود؟');
            if (!confirmed) return;
            try {
                await archiveRequestJson(`/api/v1/archive/documents/${id}`, { method: 'DELETE' });
                if (typeof showToast === 'function') showToast('سند حذف شد.', 'success');
                await archiveLoadFiles();
            } catch (error) {
                alert(`خطا در حذف سند.\nجزئیات: ${String(error?.message || '')}`);
            }
        }

        async function archiveSendTransmittalFromRow(docNumber, projectCode, disciplineCode, revision) {
            const normalizedDoc = String(docNumber || '').trim();
            if (!normalizedDoc) return;
            if (typeof window.setPendingTransmittalDoc === 'function') {
                window.setPendingTransmittalDoc({
                    doc_number: normalizedDoc,
                    project_code: String(projectCode || '').trim().toUpperCase(),
                    discipline_code: String(disciplineCode || '').trim().toUpperCase(),
                    revision: String(revision || '00').trim() || '00',
                    status: 'IFA',
                });
            }
            if (typeof window.navigateTo === 'function') {
                await window.navigateTo('view-transmittal');
                setTimeout(() => {
                    if (typeof window.showCreateMode === 'function') {
                        window.showCreateMode();
                    }
                }, 0);
            }
        }

        async function archiveOpenHistory(documentId, docNumber) {
            const id = Number(documentId || 0);
            if (!id) {
                alert('Document id not found.');
                return;
            }
            const modal = document.getElementById('archiveHistoryModal');
            const meta = document.getElementById('archiveHistoryMeta');
            const body = document.getElementById('archiveHistoryBody');
            meta.innerHTML = `<b>Doc:</b> <span style="font-family:monospace;">${archiveEsc(docNumber || '-')}</span>`;
            body.innerHTML = '<div style="text-align:center; color:#94a3b8;">Loading...</div>';
            modal.style.display = 'flex';

            try {
                const response = await window.fetchWithAuth(`/api/v1/archive/revision-history/${id}`);
                const payload = await response.json();
                if (!payload.ok) {
                    body.innerHTML = '<div style="text-align:center; color:#ef4444;">Failed to load revision history.</div>';
                    return;
                }
                const revisions = Array.isArray(payload.revisions) ? payload.revisions : [];
                if (!revisions.length) {
                    body.innerHTML = '<div style="text-align:center; color:#94a3b8;">No revisions found.</div>';
                    return;
                }
                body.innerHTML = revisions.map((rev) => {
                    const files = Array.isArray(rev.files) ? rev.files : [];
                    const fileRows = files.length ? files.map((item) => {
                        const fileSize = item.size ? `${(item.size / 1024).toFixed(1)} KB` : '-';
                        const uploadedAt = formatShamsiDateTime(item.uploaded_at);
                        return `
                            <tr>
                                <td>${archiveEsc(item.file_kind)}</td>
                                <td style="direction:ltr;text-align:right;">${archiveEsc(item.name)}</td>
                                <td>${fileSize}</td>
                                <td>${uploadedAt}</td>
                                <td>
                                    <button class="btn-archive-icon" data-archive-action="download-file" data-file-id="${Number(item.id || 0)}">
                                        <span class="material-icons-round" style="font-size:18px;">download</span>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }).join('') : '<tr><td colspan="5" style="text-align:center; color:#94a3b8;">No files</td></tr>';

                    return `
                        <div style="border:1px solid #e5e7eb; border-radius:8px; margin-bottom:10px; overflow:hidden;">
                            <div style="padding:8px 10px; background:#f8fafc; display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
                                <span class="file-badge">Rev ${archiveEsc(rev.revision || '-')}</span>
                                <span style="color:#64748b;">Status: ${archiveEsc(rev.status || '-')}</span>
                                <span style="color:#94a3b8;">${formatShamsiDateTime(rev.created_at)}</span>
                            </div>
                            <div style="padding:10px;">
                                <table class="archive-table" style="width:100%;">
                                    <thead>
                                        <tr>
                                            <th style="width:90px;">Kind</th>
                                            <th>Name</th>
                                            <th style="width:90px;">Size</th>
                                            <th style="width:180px;">Uploaded</th>
                                            <th style="width:70px;">Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>${fileRows}</tbody>
                                </table>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (error) {
                console.error(error);
                body.innerHTML = '<div style="text-align:center; color:#ef4444;">Failed to load revision history.</div>';
            }
        }

        function archiveCloseHistoryModal() {
            document.getElementById('archiveHistoryModal').style.display = 'none';
        }

        function archiveDebouncedSearch() { clearTimeout(window.archiveSearchTimer); window.archiveSearchTimer = setTimeout(()=>archiveLoadFiles(), 500); }
        function archiveOpenModal() { document.getElementById('archiveUploadModal').style.display='flex'; archiveResetForm(); }
        function archiveCloseModal() { document.getElementById('archiveUploadModal').style.display='none'; }
        function archiveResetForm() {
            document.getElementById('archiveUploadForm').reset();
            document.getElementById('archivePdfFileName').innerText = '';
            document.getElementById('archiveNativeFileName').innerText = '';
            archiveSetDropzoneState('pdf', 'idle');
            archiveSetDropzoneState('native', 'idle');
            archiveSetValidationMessage('pdf', '');
            archiveSetValidationMessage('native', '');
            document.getElementById('docStatusMsg').innerHTML = '';
            const list = document.getElementById('archiveDocCodeSuggestions');
            if (list) list.innerHTML = '';
            const fullMsg = document.getElementById('fullDocCheckMsg');
            if (fullMsg) fullMsg.innerHTML = '';
            const fullRegBtn = document.getElementById('fullRegisterDocBtn');
            if (fullRegBtn) fullRegBtn.style.display = 'none';
            document.getElementById('fullDocNumber').value = '';
            document.getElementById('realDocId').value = '';
            isFullMode = true;
            toggleRegistrationMode();
        }

        async function archiveOpenModalForDocument(documentId, docNumber) {
            const normalizedDocNumber = archiveNormalizeDocCode(docNumber);
            const resolvedDocumentId = Number(documentId || 0);
            archiveOpenModal();
            const smartDocCodeInput = document.getElementById('smartDocCode');
            if (smartDocCodeInput && normalizedDocNumber) {
                smartDocCodeInput.value = normalizedDocNumber;
            }
            if (resolvedDocumentId > 0) {
                document.getElementById('realDocId').value = String(resolvedDocumentId);
            }
            archiveRefreshSubmitButtonState();
            if (normalizedDocNumber) {
                await checkDocStatus();
            }
        }

        function archiveOnFileSelect(input, kind = 'pdf') {
            const file = input?.files?.[0];
            if (!file) {
                archiveSetDropzoneState(kind, 'idle');
                archiveSetValidationMessage(kind, '');
                archiveRefreshSubmitButtonState();
                return;
            }

            const check = archiveValidateFileByKind(file, kind);
            if (!check.ok) {
                if (input) input.value = '';
                archiveSetDropzoneState(kind, 'invalid');
                archiveSetValidationMessage(kind, check.message, 'error');
                if (kind === 'native') {
                    document.getElementById('archiveNativeFileName').innerText = '';
                } else {
                    document.getElementById('archivePdfFileName').innerText = '';
                }
                archiveRefreshSubmitButtonState();
                return;
            }

            archiveSetDropzoneState(kind, 'valid');
            archiveSetValidationMessage(kind, check.message, 'success');

            if (kind === 'native') {
                document.getElementById('archiveNativeFileName').innerText = `${file.name} - ${archiveFormatFileSize(file.size)}`;
                archiveRefreshSubmitButtonState();
                return;
            }

            document.getElementById('archivePdfFileName').innerText = `${file.name} - ${archiveFormatFileSize(file.size)}`;
            if (!isFullMode) {
                const m = file.name.match(/[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9]+/);
                if (m) {
                    document.getElementById('smartDocCode').value = m[0];
                    checkDocStatus();
                }
            }
            archiveRefreshSubmitButtonState();
        }

        function archiveBindUiEvents() {
            const root = document.getElementById('view-archive');
            if (!root) return;
            if (archiveUiEventsBound && archiveUiEventsRoot === root) return;
            archiveUiEventsBound = true;
            archiveUiEventsRoot = root;

            const searchInput = document.getElementById('archiveSearchInput');
            const projectFilter = document.getElementById('archiveProjectFilter');
            const disciplineFilter = document.getElementById('archiveDisciplineFilter');
            const statusFilter = document.getElementById('archiveStatusFilter');
            const filePresenceFilter = document.getElementById('archiveFilePresenceFilter');
            const dateFromFilter = document.getElementById('archiveDateFromFilter');
            const dateToFilter = document.getElementById('archiveDateToFilter');

            searchInput?.addEventListener('keyup', archiveDebouncedSearch);
            [projectFilter, disciplineFilter, statusFilter, filePresenceFilter, dateFromFilter, dateToFilter].forEach((el) => {
                el?.addEventListener('change', archiveApplyFilters);
            });

            const uploadForm = document.getElementById('archiveUploadForm');
            uploadForm?.addEventListener('submit', archiveHandleUpload);

            const smartDocCode = document.getElementById('smartDocCode');
            smartDocCode?.addEventListener('input', archiveOnDocCodeInput);
            smartDocCode?.addEventListener('keydown', archiveHandleDocCodeKey);

            const pdfInput = document.getElementById('archivePdfFileInput');
            const nativeInput = document.getElementById('archiveNativeFileInput');
            const pdfDropzone = document.getElementById('archivePdfDropzone');
            const nativeDropzone = document.getElementById('archiveNativeDropzone');

            pdfInput?.addEventListener('change', () => archiveOnFileSelect(pdfInput, 'pdf'));
            nativeInput?.addEventListener('change', () => archiveOnFileSelect(nativeInput, 'native'));
            pdfDropzone?.addEventListener('click', () => pdfInput?.click());
            nativeDropzone?.addEventListener('click', () => nativeInput?.click());

            const regProject = document.getElementById('regProject');
            const regDisc = document.getElementById('regDisc');
            const regMdr = document.getElementById('regMdr');
            const regPhase = document.getElementById('regPhase');
            const regPkg = document.getElementById('regPkg');
            const regBlock = document.getElementById('regBlock');
            const regLevel = document.getElementById('regLevel');
            const regSubject = document.getElementById('regSubject');
            const regSubjectE = document.getElementById('regSubjectE');
            const regSubjectP = document.getElementById('regSubjectP');

            regProject?.addEventListener('change', onProjectChange);
            regDisc?.addEventListener('change', onDisciplineChange);
            [regMdr, regPhase, regPkg, regBlock, regLevel].forEach((el) => {
                el?.addEventListener('change', updateSerialAndPreview);
            });

            const onSubjectInput = () => {
                if (window.archiveSubjectTimer) clearTimeout(window.archiveSubjectTimer);
                window.archiveSubjectTimer = setTimeout(() => updateSerialAndPreview(), 220);
            };
            regSubject?.addEventListener('input', onSubjectInput);
            regSubjectE?.addEventListener('input', onSubjectInput);
            regSubjectP?.addEventListener('input', onSubjectInput);

            root.addEventListener('click', (event) => {
                const actionEl = event.target?.closest?.('[data-archive-action]');
                if (!actionEl || !root.contains(actionEl)) return;

                const action = String(actionEl.getAttribute('data-archive-action') || '').trim();
                if (action && action !== 'toggle-row-menu') {
                    archiveCloseRowMenus();
                }
                switch (action) {
                    case 'toggle-row-menu':
                        archiveToggleRowMenu(actionEl);
                        break;
                    case 'open-modal':
                        archiveOpenModal();
                        break;
                    case 'upload-for-document':
                        archiveOpenModalForDocument(
                            Number(actionEl.getAttribute('data-document-id') || 0),
                            actionEl.getAttribute('data-doc-number') || ''
                        );
                        break;
                    case 'close-modal':
                        archiveCloseModal();
                        break;
                    case 'toggle-mode':
                        toggleRegistrationMode();
                        break;
                    case 'check-doc-status':
                        checkDocStatus();
                        break;
                    case 'register-preview-doc':
                        archiveRegisterPreviewDocument();
                        break;
                    case 'reset-filters':
                        archiveResetFilters();
                        break;
                    case 'refresh-list':
                        archiveLoadFiles();
                        break;
                    case 'close-history-modal':
                        archiveCloseHistoryModal();
                        break;
                    case 'download-kind': {
                        const pdfId = Number(actionEl.getAttribute('data-pdf-id') || 0);
                        const nativeId = Number(actionEl.getAttribute('data-native-id') || 0);
                        const kind = String(actionEl.getAttribute('data-kind') || 'pdf');
                        const encodedRel = String(actionEl.getAttribute('data-site-relative-path') || '');
                        const relativePath = encodedRel ? decodeURIComponent(encodedRel) : '';
                        const fileName = String(actionEl.getAttribute('data-file-name') || '');
                        archiveDownloadByKind(pdfId, nativeId, kind, relativePath, fileName);
                        break;
                    }
                    case 'download-latest': {
                        const pdfId = Number(actionEl.getAttribute('data-pdf-id') || 0);
                        const nativeId = Number(actionEl.getAttribute('data-native-id') || 0);
                        const encodedRel = String(actionEl.getAttribute('data-site-relative-path') || '');
                        const relativePath = encodedRel ? decodeURIComponent(encodedRel) : '';
                        const fileName = String(actionEl.getAttribute('data-file-name') || '');
                        archiveDownloadByKind(pdfId, nativeId, pdfId > 0 ? 'pdf' : 'native', relativePath, fileName);
                        break;
                    }
                    case 'open-detail':
                        archiveNavigateToDocumentDetail(Number(actionEl.getAttribute('data-document-id') || 0), false);
                        break;
                    case 'edit-detail':
                        archiveNavigateToDocumentDetail(Number(actionEl.getAttribute('data-document-id') || 0), true);
                        break;
                    case 'send-transmittal':
                        archiveSendTransmittalFromRow(
                            actionEl.getAttribute('data-doc-number') || '',
                            actionEl.getAttribute('data-project-code') || '',
                            actionEl.getAttribute('data-discipline-code') || '',
                            actionEl.getAttribute('data-revision') || '00',
                        );
                        break;
                    case 'copy-doc':
                        archiveCopyDocNumber(actionEl.getAttribute('data-doc-number') || '');
                        break;
                    case 'open-history': {
                        const documentId = Number(actionEl.getAttribute('data-document-id') || 0);
                        const docNumber = actionEl.getAttribute('data-doc-number') || '';
                        archiveOpenHistory(documentId, docNumber);
                        break;
                    }
                    case 'download-file':
                        archiveDownloadFile(Number(actionEl.getAttribute('data-file-id') || 0));
                        break;
                    case 'open-local': {
                        const encodedRel = String(actionEl.getAttribute('data-site-relative-path') || '');
                        const relativePath = encodedRel ? decodeURIComponent(encodedRel) : '';
                        archiveTryOpenLocal(relativePath, actionEl.getAttribute('data-file-name') || '');
                        break;
                    }
                    case 'toggle-pin': {
                        const fileId = Number(actionEl.getAttribute('data-file-id') || 0);
                        const isPinned = String(actionEl.getAttribute('data-pinned') || '0') === '1';
                        archiveTogglePin(fileId, !isPinned).then(() => {
                            archiveLoadFiles();
                        }).catch((error) => {
                            alert(`Ø®Ø·Ø§ Ø¯Ø± ØªØºÛŒÛŒØ± ÙˆØ¶Ø¹ÛŒØª Pin.\nØ¬Ø²Ø¦ÛŒØ§Øª: ${String(error?.message || '')}`);
                        });
                        break;
                    }
                    case 'show-integrity':
                        archiveShowIntegrity(
                            Number(actionEl.getAttribute('data-file-id') || 0),
                            actionEl.getAttribute('data-file-name') || ''
                        );
                        break;
                    case 'delete-document':
                        archiveDeleteDocument(Number(actionEl.getAttribute('data-document-id') || 0));
                        break;
                    default:
                        break;
                }
            });

            root.addEventListener('click', (event) => {
                if (!event.target?.closest?.('[data-archive-row-menu]')) {
                    archiveCloseRowMenus();
                }
            });

            document.addEventListener('click', (event) => {
                if (!root.contains(event.target)) {
                    archiveCloseRowMenus();
                }
            });

            document.getElementById('archiveUploadModal')?.addEventListener('click', (event) => {
                if (event.target?.id === 'archiveUploadModal') archiveCloseModal();
            });
            document.getElementById('archiveHistoryModal')?.addEventListener('click', (event) => {
                if (event.target?.id === 'archiveHistoryModal') archiveCloseHistoryModal();
            });
        }

        function initArchiveView(forceReload = false) {
            const root = document.getElementById('view-archive');
            if (!root) return;
            archiveBindUiEvents();
            archiveInitDropzones();
            if (forceReload) {
                archiveLoadFilterCatalog();
            }
            archiveLoadFiles();
        }

        window.initArchiveView = initArchiveView;
        window.archiveLoadFiles = archiveLoadFiles;
        window.archiveOpenModal = archiveOpenModal;
        window.archiveCloseModal = archiveCloseModal;

        if (window.AppEvents?.on) {
            window.AppEvents.on('view:loaded', ({ viewId, partialName }) => {
                if (String(viewId || '').trim() === 'view-edms' || String(partialName || '').trim() === 'edms') {
                    initArchiveView(true);
                }
            });
            window.AppEvents.on('view:activated', ({ viewId }) => {
                if (String(viewId || '').trim() === 'view-edms') {
                    initArchiveView(false);
                }
            });
        }

        initArchiveView(false);


