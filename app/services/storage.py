from __future__ import annotations

import os
import shutil
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
