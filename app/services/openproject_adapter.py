from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from requests import Response


class OpenProjectAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        connect_timeout: float = 5,
        read_timeout: float = 10,
        tls_verify: bool = True,
    ) -> None:
        self.base_url = self.normalize_base_url(base_url)
        self.api_token = str(api_token or "").strip()
        self.timeout = (float(connect_timeout), float(read_timeout))
        self.tls_verify = bool(tls_verify)
        if not self.base_url:
            raise RuntimeError("OPENPROJECT_BASE_URL is empty.")
        if not self.api_token:
            raise RuntimeError("OPENPROJECT_API_TOKEN is empty.")

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        raw = str(base_url or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            return raw.rstrip("/")
        path = re.sub(r"/api/v3/?$", "", str(parts.path or ""), flags=re.IGNORECASE).rstrip("/")
        return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")

    def _api_url(self, resource: str = "") -> str:
        suffix = str(resource or "").strip().lstrip("/")
        if not suffix:
            return f"{self.base_url}/api/v3"
        return f"{self.base_url}/api/v3/{suffix}"

    def _request(self, method: str, resource: str, **kwargs: Any) -> Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Accept", "application/json")
        return requests.request(
            method=method,
            url=self._api_url(resource),
            auth=("apikey", self.api_token),
            timeout=self.timeout,
            verify=self.tls_verify,
            headers=headers,
            **kwargs,
        )

    def ping_raw(self) -> Response:
        return self._request("GET", "")

    def ping(self) -> dict[str, Any]:
        response = self.ping_raw()
        if response.status_code >= 400:
            raise RuntimeError(f"OpenProject API ping failed: HTTP {response.status_code}")
        try:
            return response.json()
        except Exception:
            return {"ok": True, "status_code": response.status_code}

    def attach_external_link(
        self,
        *,
        work_package_id: int,
        title: str,
        url: str,
    ) -> dict[str, Any]:
        patch_payload = {
            "_links": {},
            "description": {
                "format": "markdown",
                "raw": f"{title}\n\n{url}",
            },
        }
        response = self._request(
            "PATCH",
            f"work_packages/{int(work_package_id)}",
            headers={"Content-Type": "application/json"},
            json=patch_payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject sync failed for work package {work_package_id}: HTTP {response.status_code}"
            )
        return response.json()
