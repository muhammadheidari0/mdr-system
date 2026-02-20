from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests
import urllib3
from requests import Response


class NextcloudAdapter:
    _insecure_warning_suppressed = False

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        app_password: str,
        root_path: str = "",
        connect_timeout: float = 5,
        read_timeout: float = 10,
        tls_verify: bool = True,
    ) -> None:
        self.base_url = self.normalize_base_url(base_url)
        self.username = str(username or "").strip()
        self.app_password = str(app_password or "").strip()
        self.root_path = self.normalize_root_path(root_path)
        self.timeout = (float(connect_timeout), float(read_timeout))
        self.tls_verify = bool(tls_verify)
        if not self.base_url:
            raise RuntimeError("NEXTCLOUD_BASE_URL is empty.")
        if not self.username:
            raise RuntimeError("NEXTCLOUD_USERNAME is empty.")
        if not self.app_password:
            raise RuntimeError("NEXTCLOUD_APP_PASSWORD is empty.")

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        raw = str(base_url or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            return raw.rstrip("/")
        path = str(parts.path or "").rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")

    @staticmethod
    def normalize_root_path(root_path: str) -> str:
        raw = str(root_path or "").strip().replace("\\", "/")
        if not raw:
            return "/"
        normalized = "/" + raw.strip("/")
        return normalized if normalized != "//" else "/"

    @staticmethod
    def _response_error_detail(response: Response) -> str:
        text = ""
        try:
            text = str(getattr(response, "text", "") or "").strip()
        except Exception:
            text = ""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1000]

    def build_webdav_root_url(self) -> str:
        base = self.normalize_base_url(self.base_url)
        parts = urlsplit(base)
        base_path = str(parts.path or "").strip("/")
        if base_path.endswith("remote.php/webdav") or "/remote.php/webdav/" in f"/{base_path}/":
            dav_path = f"/{base_path}"
        elif "/remote.php/dav/files/" in f"/{base_path}/":
            dav_path = f"/{base_path}"
        else:
            prefix = f"/{base_path}" if base_path else ""
            dav_path = f"{prefix}/remote.php/dav/files/{quote(self.username, safe='')}"
        root = self.normalize_root_path(self.root_path)
        if root and root != "/":
            dav_path = f"{dav_path.rstrip('/')}{root}"
        return urlunsplit((parts.scheme, parts.netloc, dav_path.rstrip("/"), "", ""))

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        if not self.tls_verify and not NextcloudAdapter._insecure_warning_suppressed:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            NextcloudAdapter._insecure_warning_suppressed = True
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept", "*/*")
        return requests.request(
            method=method,
            url=str(url or "").strip(),
            auth=(self.username, self.app_password),
            timeout=self.timeout,
            verify=self.tls_verify,
            headers=headers,
            **kwargs,
        )

    def ping_raw(self) -> Response:
        url = self.build_webdav_root_url()
        response = self._request("PROPFIND", url, headers={"Depth": "0"})
        if int(response.status_code or 0) == 405:
            response = self._request("GET", url)
        return response

    def ping(self) -> dict[str, Any]:
        response = self.ping_raw()
        return {
            "status_code": int(response.status_code or 0),
            "ok": int(response.status_code or 0) < 400,
        }

    def ensure_path(self, remote_dir: str) -> str:
        parts = [
            part
            for part in str(remote_dir or "").strip().replace("\\", "/").split("/")
            if str(part or "").strip()
        ]
        current_url = self.build_webdav_root_url().rstrip("/")
        for part in parts:
            current_url = f"{current_url}/{quote(str(part), safe='')}"
            response = self._request("MKCOL", current_url)
            if int(response.status_code or 0) in {200, 201, 204, 301, 302, 405}:
                continue
            if int(response.status_code or 0) == 409:
                probe = self._request("PROPFIND", current_url, headers={"Depth": "0"})
                if int(probe.status_code or 0) in {200, 207, 301, 302}:
                    continue
            if int(response.status_code or 0) >= 400:
                detail = self._response_error_detail(response)
                message = f"Nextcloud path ensure failed: HTTP {response.status_code}"
                if detail:
                    message = f"{message} :: {detail}"
                raise RuntimeError(message)
        return current_url

    def upload_file(
        self,
        *,
        local_path: str,
        remote_relative_path: str,
    ) -> dict[str, str]:
        path = Path(str(local_path or "").strip())
        if not path.exists():
            raise RuntimeError(f"Local file not found for Nextcloud mirror: {local_path}")

        remote = str(remote_relative_path or "").strip().replace("\\", "/").lstrip("/")
        if not remote:
            raise RuntimeError("remote_relative_path is required for Nextcloud upload.")
        segments = [part for part in remote.split("/") if part]
        if not segments:
            raise RuntimeError("remote_relative_path is invalid for Nextcloud upload.")

        folder_segments = segments[:-1]
        file_name = segments[-1]
        if folder_segments:
            self.ensure_path("/".join(folder_segments))

        root_url = self.build_webdav_root_url().rstrip("/")
        encoded_segments = "/".join(quote(part, safe="") for part in segments)
        remote_url = f"{root_url}/{encoded_segments}"
        with open(path, "rb") as stream:
            response = self._request("PUT", remote_url, data=stream)
        if int(response.status_code or 0) >= 400:
            detail = self._response_error_detail(response)
            message = f"Nextcloud upload failed: HTTP {response.status_code}"
            if detail:
                message = f"{message} :: {detail}"
            raise RuntimeError(message)
        return {
            "remote_id": remote,
            "remote_url": remote_url,
            "file_name": file_name,
        }
