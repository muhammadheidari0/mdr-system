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

    def upload_file(
        self,
        *,
        local_path: str,
        display_name: str,
        mime_type: str,
        folder_id: str | None = None,
    ) -> dict[str, str]:
        path = Path(local_path)
        if not path.exists():
            raise RuntimeError(f"Local file not found for drive mirror: {local_path}")

        service = self._get_service()
        try:
            from googleapiclient.http import MediaFileUpload  # type: ignore
        except Exception as exc:
            raise RuntimeError("google-api-python-client is required for MediaFileUpload.") from exc

        parent = str(folder_id or "").strip() or self.root_folder_id
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
