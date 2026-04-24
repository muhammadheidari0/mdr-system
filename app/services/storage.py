from __future__ import annotations

import os
import shutil
import ntpath
import subprocess
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SettingsKV
from app.services.file_integrity import SavedFileInfo, save_upload_with_integrity
from app.services.folder_service import safe_name
from app.services.storage_policy import get_storage_integrations, get_storage_policy, resolve_primary_storage_provider
from app.services.storage_sync import resolve_nextcloud_runtime


class StorageManager:
    """Centralized storage path resolver and file saver."""

    MDR_STORAGE_KEY = "mdr_storage_path"
    CORRESPONDENCE_STORAGE_KEY = "correspondence_storage_path"
    DEFAULT_MDR_STORAGE_PATH = "./files/technical"
    DEFAULT_CORRESPONDENCE_STORAGE_PATH = "./files/correspondence"

    def __init__(self, db: Session):
        self.db = db

    def _get_setting(self, key: str, default: str) -> str:
        row = self.db.query(SettingsKV).filter(SettingsKV.key == key).first()
        value = str(row.value).strip() if row and row.value is not None else ""
        return value or default

    @staticmethod
    def _resolve_path(path_value: str) -> Path:
        path = Path(path_value).expanduser()
        if path.is_absolute():
            return path
        return Path(settings.BASE_DIR) / path

    @staticmethod
    def _has_uri_scheme(value: str) -> bool:
        text = str(value or "").strip()
        return "://" in text

    @staticmethod
    def _is_unc_path(value: str) -> bool:
        text = str(value or "").strip().replace("/", "\\")
        if not text.startswith("\\\\"):
            return False
        parts = [part for part in text.split("\\") if part]
        return len(parts) >= 2

    @classmethod
    def _normalize_unc_path(cls, value: str) -> str:
        text = str(value or "").strip().replace("/", "\\")
        normalized = ntpath.normpath(text)
        if not normalized.startswith("\\\\"):
            normalized = "\\\\" + normalized.lstrip("\\")
        return normalized.rstrip("\\")

    @classmethod
    def _normalize_unc_root(cls, value: str) -> str:
        return cls._normalize_unc_path(value).rstrip("\\")

    @classmethod
    def _is_under_unc_root(cls, path_value: str, root_value: str) -> bool:
        path_norm = cls._normalize_unc_root(path_value)
        root_norm = cls._normalize_unc_root(root_value)
        if not root_norm:
            return False
        path_cmp = path_norm.lower()
        root_cmp = root_norm.lower()
        return path_cmp == root_cmp or path_cmp.startswith(f"{root_cmp}\\")

    @classmethod
    def _extract_unc_share_root(cls, value: str) -> str:
        normalized = cls._normalize_unc_path(value)
        parts = [part for part in normalized.split("\\") if part]
        if len(parts) < 2:
            raise ValueError("Invalid UNC path.")
        return f"\\\\{parts[0]}\\{parts[1]}"

    @classmethod
    def _ensure_unc_connected_with_credentials(
        cls,
        *,
        unc_path: str,
        username: str,
        password: str,
    ) -> None:
        user = str(username or "").strip()
        if not user:
            return
        if password is None:
            return
        if os.name != "nt":
            raise RuntimeError(
                "Runtime cannot mount UNC credentials directly. Configure OS-level mount/service account."
            )
        share_root = cls._extract_unc_share_root(unc_path)
        command = [
            "net",
            "use",
            share_root,
            str(password),
            f"/user:{user}",
            "/persistent:no",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0:
            return
        stderr = str(result.stderr or "").strip()
        stdout = str(result.stdout or "").strip()
        detail = stderr or stdout or f"exit={result.returncode}"
        raise RuntimeError(f"UNC authentication failed for share {share_root}: {detail}")

    @classmethod
    def _default_allowed_roots(cls) -> list[Path]:
        roots: list[Path] = []
        mdr_data_root = str(getattr(settings, "MDR_DATA_ROOT", "") or "").strip()
        if mdr_data_root:
            roots.append(Path(mdr_data_root) / "archive_storage")
            roots.append(Path(mdr_data_root) / "data_store")

        base = Path(settings.BASE_DIR).resolve()
        roots.append(base / "archive_storage")
        roots.append(base / "data_store")
        roots.append(base / "files")

        # Container canonical mounts.
        roots.append(Path("/app/archive_storage"))
        roots.append(Path("/app/data_store"))

        dedup: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            try:
                resolved = root.expanduser().resolve(strict=False)
            except Exception:
                continue
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(resolved)
        return dedup

    @classmethod
    def allowed_roots(cls) -> list[Path]:
        raw = str(getattr(settings, "STORAGE_ALLOWED_ROOTS", "") or "").strip()
        if not raw:
            return cls._default_allowed_roots()

        roots: list[Path] = []
        seen: set[str] = set()
        for token in [part.strip() for part in raw.split(",")]:
            if not token or cls._has_uri_scheme(token):
                continue
            candidate = Path(token).expanduser()
            if not candidate.is_absolute():
                continue
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                continue
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            roots.append(resolved)
        return roots

    @classmethod
    def allowed_unc_roots(cls) -> list[str]:
        raw = str(getattr(settings, "STORAGE_ALLOWED_ROOTS", "") or "").strip()
        if not raw:
            return []

        roots: list[str] = []
        seen: set[str] = set()
        for token in [part.strip() for part in raw.split(",")]:
            if not token or cls._has_uri_scheme(token):
                continue
            if not cls._is_unc_path(token):
                continue
            normalized = cls._normalize_unc_root(token)
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            roots.append(normalized)
        return roots

    @staticmethod
    def _is_under_root(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath([str(path), str(root)]) == str(root)
        except Exception:
            return False

    @staticmethod
    def _probe_writable(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".storage_write_probe_{uuid.uuid4().hex}.tmp"
        try:
            with open(probe, "wb") as stream:
                stream.write(b"ok")
        finally:
            try:
                if probe.exists():
                    probe.unlink()
            except Exception:
                pass

    @classmethod
    def validate_storage_path(
        cls,
        path_value: str,
        *,
        field: str,
        network_username: str | None = None,
        network_password: str | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        raw = str(path_value or "").strip()
        if not raw:
            errors.append(
                {
                    "field": field,
                    "code": "path_required",
                    "message": "Path cannot be empty.",
                }
            )
            return "", errors

        if cls._has_uri_scheme(raw):
            errors.append(
                {
                    "field": field,
                    "code": "path_scheme_not_supported",
                    "message": "Network URI schemes (e.g. smb://) are not supported. Use mounted filesystem paths.",
                }
            )
            return "", errors

        is_unc_path = cls._is_unc_path(raw)
        candidate = Path(raw).expanduser()
        require_absolute = bool(getattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True))
        if require_absolute and not (candidate.is_absolute() or is_unc_path):
            errors.append(
                {
                    "field": field,
                    "code": "path_not_absolute",
                    "message": "Path must be absolute.",
                }
            )
            return "", errors

        if is_unc_path:
            normalized_unc = cls._normalize_unc_path(raw)
            configured_roots_raw = str(getattr(settings, "STORAGE_ALLOWED_ROOTS", "") or "").strip()
            unc_roots = cls.allowed_unc_roots()
            if configured_roots_raw and unc_roots:
                if not any(cls._is_under_unc_root(normalized_unc, root) for root in unc_roots):
                    allowed = ", ".join(unc_roots)
                    errors.append(
                        {
                            "field": field,
                            "code": "path_outside_allowed_roots",
                            "message": f"Path must be under allowed roots: {allowed}",
                        }
                    )
                    return "", errors
            elif configured_roots_raw and not unc_roots:
                errors.append(
                    {
                        "field": field,
                        "code": "path_outside_allowed_roots",
                        "message": "UNC paths are not included in STORAGE_ALLOWED_ROOTS.",
                    }
                )
                return "", errors

            validate_writable = bool(getattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True))
            if validate_writable:
                try:
                    if network_username and network_password is not None:
                        cls._ensure_unc_connected_with_credentials(
                            unc_path=normalized_unc,
                            username=network_username,
                            password=network_password,
                        )
                    cls._probe_writable(Path(normalized_unc))
                except Exception as exc:
                    code = "path_not_writable"
                    message = "Path is not writable by the service account."
                    if network_username:
                        code = "path_unc_auth_failed"
                        if isinstance(exc, RuntimeError) and "cannot mount UNC credentials" in str(exc):
                            message = "UNC credential mounting is not supported by this runtime. Configure OS-level mount."
                        else:
                            message = "UNC authentication failed or share is not writable."
                    errors.append({"field": field, "code": code, "message": message})
                    return "", errors
            return normalized_unc, errors

        if not candidate.is_absolute():
            candidate = Path(settings.BASE_DIR) / candidate

        try:
            normalized = candidate.resolve(strict=False)
        except Exception:
            errors.append(
                {
                    "field": field,
                    "code": "path_invalid",
                    "message": "Path is invalid.",
                }
            )
            return "", errors

        roots = cls.allowed_roots()
        if roots and not any(cls._is_under_root(normalized, root) for root in roots):
            allowed = ", ".join(str(root) for root in roots)
            errors.append(
                {
                    "field": field,
                    "code": "path_outside_allowed_roots",
                    "message": f"Path must be under allowed roots: {allowed}",
                }
            )
            return "", errors

        validate_writable = bool(getattr(settings, "STORAGE_VALIDATE_WRITABLE_ON_SAVE", True))
        if validate_writable:
            try:
                cls._probe_writable(normalized)
            except Exception:
                errors.append(
                    {
                        "field": field,
                        "code": "path_not_writable",
                        "message": "Path is not writable by the service account.",
                    }
                )
                return "", errors

        return str(normalized), errors

    def get_mdr_base_path(self) -> Path:
        raw = self._get_setting(self.MDR_STORAGE_KEY, self.DEFAULT_MDR_STORAGE_PATH)
        return self._resolve_path(raw)

    def get_correspondence_base_path(self) -> Path:
        raw = self._get_setting(
            self.CORRESPONDENCE_STORAGE_KEY,
            self.DEFAULT_CORRESPONDENCE_STORAGE_PATH,
        )
        return self._resolve_path(raw)

    @classmethod
    def _path_is_under_root_value(cls, path_value: str, root_value: str) -> bool:
        raw_path = str(path_value or "").strip()
        raw_root = str(root_value or "").strip()
        if not raw_path or not raw_root:
            return False

        path_is_unc = cls._is_unc_path(raw_path)
        root_is_unc = cls._is_unc_path(raw_root)
        if path_is_unc or root_is_unc:
            if not (path_is_unc and root_is_unc):
                return False
            try:
                return cls._is_under_unc_root(raw_path, raw_root)
            except Exception:
                return False

        try:
            normalized_path = cls._resolve_path(raw_path).resolve(strict=False)
            normalized_root = cls._resolve_path(raw_root).resolve(strict=False)
        except Exception:
            return False
        return cls._is_under_root(normalized_path, normalized_root)

    def get_selected_primary_storage_provider(self) -> str:
        integrations = get_storage_integrations(self.db)
        return resolve_primary_storage_provider(integrations)

    def resolve_storage_backend_for_path(self, path_value: str) -> str:
        integrations = get_storage_integrations(self.db)
        if resolve_primary_storage_provider(integrations) != "nextcloud":
            return "local"

        runtime = resolve_nextcloud_runtime(integrations)
        mount_root = str(runtime.get("local_mount_root_effective") or "").strip()
        if mount_root and self._path_is_under_root_value(path_value, mount_root):
            return "nextcloud"
        return "local"

    def get_mdr_path(
        self,
        *,
        project_code: str,
        project_name: str | None,
        mdr_folder_name: str,
        phase_name: str,
        disc_name: str,
        disc_code: str,
        pkg_name: str,
        pkg_code: str,
        phase_code: str | None = None,
        package_name: str | None = None,
        file_kind: str | None = None,
        project_root_path: str | None = None,
    ) -> str:
        """
        Build and create MDR storage path.
        Order: root / project / mdr / phase-code / discipline-code / package-name / file-kind
        """
        base = self._resolve_path(project_root_path) if project_root_path else self.get_mdr_base_path()

        safe_project_code = safe_name(project_code)
        safe_project_name = safe_name(project_name)
        if safe_project_name and safe_project_name.lower() != "unk":
            project_folder = f"{safe_project_code} - {safe_project_name}"
        else:
            project_folder = safe_project_code

        phase_folder = safe_name(phase_code or phase_name) or "Phase"
        safe_disc_code = safe_name(disc_code) or "GN"

        safe_pkg_code = safe_name(pkg_code)
        safe_pkg_name = safe_name(package_name or pkg_name)
        pkg_folder = safe_pkg_name or safe_pkg_code

        full_path = (
            base
            / safe_name(project_folder)
            / safe_name(mdr_folder_name)
            / phase_folder
            / safe_disc_code
            / safe_name(pkg_folder)
        )
        if file_kind:
            full_path = full_path / safe_name(file_kind)
        full_path.mkdir(parents=True, exist_ok=True)
        return str(full_path)

    @staticmethod
    def save_upload(file: UploadFile, destination_folder: str, new_name: str | None = None) -> str:
        """
        Save an uploaded file and return its absolute/relative path as string.
        """
        dest_path = Path(destination_folder)
        dest_path.mkdir(parents=True, exist_ok=True)

        filename = safe_name(new_name) if new_name else safe_name(file.filename)
        file_path = dest_path / filename

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception:
            if file_path.exists():
                os.remove(file_path)
            raise

        return str(file_path)

    def save_upload_secure(
        self,
        *,
        file: UploadFile,
        destination_folder: str,
        new_name: str | None = None,
        file_kind: str = "attachment",
    ) -> SavedFileInfo:
        filename = safe_name(new_name) if new_name else safe_name(file.filename)
        if not filename:
            raise ValueError("File name is empty after normalization.")
        policy = get_storage_policy(self.db)
        return save_upload_with_integrity(
            file=file,
            destination_folder=destination_folder,
            new_name=filename,
            file_kind=file_kind,
            policy=policy,
        )
