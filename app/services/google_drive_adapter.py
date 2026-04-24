from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GoogleDriveAdapter:
    def __init__(
        self,
        *,
        service_account_json: str,
        shared_drive_id: str = "",
        root_folder_id: str = "",
    ) -> None:
        self.service_account_json = str(service_account_json or "").strip()
        self.shared_drive_id = str(shared_drive_id or "").strip()
        self.root_folder_id = str(root_folder_id or "").strip()
        self._service = None

    def _load_credentials_info(self) -> dict[str, Any]:
        raw = self.service_account_json
        if not raw:
            raise RuntimeError("GDRIVE_SERVICE_ACCOUNT_JSON is empty.")
        candidate = Path(raw)
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
        return json.loads(raw)

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "Google Drive dependencies are missing. Install google-api-python-client and google-auth."
            ) from exc

        credentials_info = self._load_credentials_info()
        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = service_account.Credentials.from_service_account_info(credentials_info, scopes=scopes)
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    @staticmethod
    def _escape_query_value(value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace("'", "\\'")

    def _list_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "spaces": "drive",
            "pageSize": 1,
            "fields": "files(id, name)",
        }
        if self.shared_drive_id:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = self.shared_drive_id
        return kwargs

    def _find_folder(self, *, parent_id: str | None, name: str) -> str | None:
        service = self._get_service()
        escaped_name = self._escape_query_value(name)
        query = (
            "mimeType='application/vnd.google-apps.folder' "
            "and trashed=false "
            f"and name='{escaped_name}'"
        )
        parent = str(parent_id or "").strip()
        if parent:
            query += f" and '{self._escape_query_value(parent)}' in parents"
        kwargs = self._list_kwargs()
        kwargs["q"] = query
        response = service.files().list(**kwargs).execute()
        files = response.get("files") or []
        if not files:
            return None
        return str(files[0].get("id") or "").strip() or None

    def _create_folder(self, *, parent_id: str | None, name: str) -> str:
        service = self._get_service()
        metadata: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        parent = str(parent_id or "").strip()
        if parent:
            metadata["parents"] = [parent]
        response = service.files().create(
            body=metadata,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        folder_id = str(response.get("id") or "").strip()
        if not folder_id:
            raise RuntimeError("Google Drive folder creation returned empty id.")
        return folder_id

    def ensure_folder_path(self, folder_path: str) -> str | None:
        segments = [part.strip() for part in str(folder_path or "").replace("\\", "/").split("/") if part.strip()]
        if not segments:
            return self.root_folder_id or None

        parent_id = self.root_folder_id or None
        for segment in segments:
            existing_id = self._find_folder(parent_id=parent_id, name=segment)
            parent_id = existing_id or self._create_folder(parent_id=parent_id, name=segment)
        return parent_id

    def upload_file(
        self,
        *,
        local_path: str,
        display_name: str,
        mime_type: str,
        folder_id: str | None = None,
        folder_path: str | None = None,
    ) -> dict[str, str]:
        path = Path(local_path)
        if not path.exists():
            raise RuntimeError(f"Local file not found for drive mirror: {local_path}")

        service = self._get_service()
        try:
            from googleapiclient.http import MediaFileUpload  # type: ignore
        except Exception as exc:
            raise RuntimeError("google-api-python-client is required for MediaFileUpload.") from exc

        parent = str(folder_id or "").strip()
        if not parent and folder_path:
            parent = str(self.ensure_folder_path(folder_path) or "").strip()
        parent = parent or self.root_folder_id
        metadata: dict[str, Any] = {"name": str(display_name or path.name)}
        if parent:
            metadata["parents"] = [parent]

        media = MediaFileUpload(str(path), mimetype=str(mime_type or "application/octet-stream"), resumable=False)
        request = service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        response = request.execute()
        file_id = str(response.get("id") or "").strip()
        if not file_id:
            raise RuntimeError("Google Drive upload succeeded but returned empty file id.")
        web_view_link = str(response.get("webViewLink") or "").strip()
        return {"file_id": file_id, "web_view_link": web_view_link}
