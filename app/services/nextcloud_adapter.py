from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

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

    @staticmethod
    def normalize_browse_path(path: str) -> str:
        raw = str(path or "").strip().replace("\\", "/")
        if not raw:
            return "/"
        tokens = [token for token in raw.split("/") if token]
        if any(token in {".", ".."} for token in tokens):
            raise ValueError("Path traversal is not allowed.")
        return "/" + "/".join(tokens) if tokens else "/"

    def _url_for_relative_path(self, relative_path: str) -> str:
        normalized = self.normalize_browse_path(relative_path)
        root_url = self.build_webdav_root_url().rstrip("/")
        if normalized == "/":
            return root_url
        encoded_segments = "/".join(quote(token, safe="") for token in normalized.strip("/").split("/"))
        return f"{root_url}/{encoded_segments}"

    @staticmethod
    def _extract_href_path(raw_href: str) -> str:
        href = str(raw_href or "").strip()
        if not href:
            return ""
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc:
            value = parsed.path
        else:
            value = href
        return unquote(str(value or "")).strip()

    def list_directories(self, path: str = "/") -> dict[str, Any]:
        current_path = self.normalize_browse_path(path)
        target_url = self._url_for_relative_path(current_path).rstrip("/")
        response = self._request(
            "PROPFIND",
            target_url,
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
            data=(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
                "<d:displayname/></d:prop></d:propfind>"
            ),
        )
        status_code = int(response.status_code or 0)
        if status_code >= 400:
            detail = self._response_error_detail(response)
            message = f"Nextcloud list directories failed: HTTP {status_code}"
            if detail:
                message = f"{message} :: {detail}"
            raise RuntimeError(message)

        try:
            root = ET.fromstring(str(response.text or ""))
        except ET.ParseError as exc:
            raise RuntimeError("Nextcloud returned invalid XML response.") from exc

        current_dav_path = unquote(str(urlsplit(target_url).path or "")).rstrip("/")
        prefix = f"{current_dav_path}/" if current_dav_path else "/"
        folder_names: set[str] = set()
        for response_el in root.findall(".//{DAV:}response"):
            has_collection = bool(
                response_el.findall(".//{DAV:}resourcetype/{DAV:}collection")
            )
            if not has_collection:
                continue
            href_el = response_el.find("{DAV:}href")
            href_path = self._extract_href_path(href_el.text if href_el is not None else "")
            if not href_path:
                continue
            href_path = href_path.rstrip("/")
            if not href_path:
                continue
            if href_path == current_dav_path:
                continue
            if not href_path.startswith(prefix):
                continue
            tail = href_path[len(prefix) :].strip("/")
            if not tail:
                continue
            first_segment = tail.split("/", 1)[0].strip()
            if first_segment:
                folder_names.add(first_segment)

        folders: list[dict[str, str]] = []
        for name in sorted(folder_names, key=lambda item: item.casefold()):
            folder_path = (
                f"{current_path.rstrip('/')}/{name}"
                if current_path != "/"
                else f"/{name}"
            )
            folders.append({"name": name, "path": folder_path})
        return {"current_path": current_path, "folders": folders}

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

    def upload_file_from_stream(
        self,
        *,
        file_stream,
        remote_relative_path: str,
    ) -> dict[str, str]:
        """Upload file from stream (for FastAPI UploadFile objects)."""
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

        response = self._request("PUT", remote_url, data=file_stream)
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

    def download_file_stream(self, remote_relative_path: str):
        """Stream file in chunks for large files (generator)."""
        url = self._url_for_relative_path(remote_relative_path)
        response = self._request("GET", url, stream=True)
        if int(response.status_code or 0) >= 400:
            detail = self._response_error_detail(response)
            message = f"Nextcloud download failed: HTTP {response.status_code}"
            if detail:
                message = f"{message} :: {detail}"
            raise RuntimeError(message)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    def file_exists(self, remote_relative_path: str) -> bool:
        """Check if file exists via PROPFIND."""
        url = self._url_for_relative_path(remote_relative_path)
        try:
            response = self._request("PROPFIND", url, headers={"Depth": "0"})
            return int(response.status_code or 0) in {200, 207}
        except Exception:
            return False

    def get_file_size(self, remote_relative_path: str) -> int:
        """Get file size via PROPFIND getcontentlength."""
        url = self._url_for_relative_path(remote_relative_path)
        try:
            response = self._request(
                "PROPFIND",
                url,
                headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
                data='<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>',
            )
            if int(response.status_code or 0) >= 400:
                return 0
            root = ET.fromstring(response.text)
            size_el = root.find(".//{DAV:}getcontentlength")
            return int(size_el.text) if size_el is not None else 0
        except Exception:
            return 0

    def delete_file(self, remote_relative_path: str) -> bool:
        """Delete file via DELETE."""
        url = self._url_for_relative_path(remote_relative_path)
        try:
            response = self._request("DELETE", url)
            return int(response.status_code or 0) in {200, 204}
        except Exception:
            return False
