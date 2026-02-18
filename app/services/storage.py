from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SettingsKV
from app.services.file_integrity import SavedFileInfo, save_upload_with_integrity
from app.services.folder_service import safe_name
from app.services.storage_policy import get_storage_policy


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
    def validate_storage_path(cls, path_value: str, *, field: str) -> tuple[str, list[dict[str, str]]]:
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

        candidate = Path(raw).expanduser()
        require_absolute = bool(getattr(settings, "STORAGE_REQUIRE_ABSOLUTE_PATHS", True))
        if require_absolute and not candidate.is_absolute():
            errors.append(
                {
                    "field": field,
                    "code": "path_not_absolute",
                    "message": "Path must be absolute.",
                }
            )
            return "", errors

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
        project_root_path: str | None = None,
    ) -> str:
        """
        Build and create MDR storage path.
        Order: root / project / mdr / phase / discipline / package
        """
        base = self._resolve_path(project_root_path) if project_root_path else self.get_mdr_base_path()

        safe_project_code = safe_name(project_code)
        safe_project_name = safe_name(project_name)
        if safe_project_name and safe_project_name.lower() != "unk":
            project_folder = f"{safe_project_code} - {safe_project_name}"
        else:
            project_folder = safe_project_code

        safe_disc_code = safe_name(disc_code)
        safe_disc_name = safe_name(disc_name)
        disc_folder = f"{safe_disc_code}-{safe_disc_name}" if safe_disc_name else safe_disc_code

        safe_pkg_code = safe_name(pkg_code)
        safe_pkg_name = safe_name(pkg_name)
        pkg_folder = f"{safe_pkg_code}-{safe_pkg_name}" if safe_pkg_name else safe_pkg_code

        full_path = (
            base
            / safe_name(project_folder)
            / safe_name(mdr_folder_name)
            / safe_name(phase_name)
            / safe_name(disc_folder)
            / safe_name(pkg_folder)
        )
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
