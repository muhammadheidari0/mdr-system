from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.parse import quote

import requests
import urllib3
from requests import Response


class OpenProjectAdapter:
    _insecure_warning_suppressed = False

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

    @staticmethod
    def _project_ref(project_ref: str | int) -> str:
        value = str(project_ref or "").strip()
        if not value:
            raise RuntimeError("OpenProject project reference is empty.")
        return quote(value, safe="")

    def _request(self, method: str, resource: str, **kwargs: Any) -> Response:
        if not self.tls_verify and not OpenProjectAdapter._insecure_warning_suppressed:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            OpenProjectAdapter._insecure_warning_suppressed = True
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

    def get_work_package(self, work_package_id: int) -> dict[str, Any]:
        response = self._request("GET", f"work_packages/{int(work_package_id)}")
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject work package fetch failed for {work_package_id}: HTTP {response.status_code}"
            )
        return response.json()

    def create_work_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            "work_packages",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject work package create failed: HTTP {response.status_code}"
            )
        return response.json()

    def get_project(self, project_ref: str | int) -> dict[str, Any]:
        encoded_ref = self._project_ref(project_ref)
        response = self._request("GET", f"projects/{encoded_ref}")
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject project fetch failed for `{project_ref}`: HTTP {response.status_code}"
            )
        return response.json()

    def list_project_work_packages_page(
        self,
        project_ref: str | int,
        *,
        skip: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        safe_skip = max(0, int(skip or 0))
        safe_limit = max(1, min(1000, int(limit or 200)))
        encoded_ref = self._project_ref(project_ref)
        response = self._request(
            "GET",
            f"projects/{encoded_ref}/work_packages",
            params={"offset": safe_skip, "pageSize": safe_limit},
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject project work packages list failed for `{project_ref}`: HTTP {response.status_code}"
            )
        payload = response.json()
        embedded = payload.get("_embedded") if isinstance(payload, dict) else None
        items = (
            embedded.get("elements")
            if isinstance(embedded, dict) and isinstance(embedded.get("elements"), list)
            else []
        )
        total = int(payload.get("total") or len(items)) if isinstance(payload, dict) else len(items)
        return {
            "project_ref": str(project_ref),
            "items": items,
            "total": max(0, total),
            "skip": safe_skip,
            "limit": safe_limit,
        }

    def iter_project_work_packages(
        self,
        project_ref: str | int,
        *,
        page_size: int = 200,
        max_items: int = 5000,
    ):
        safe_page_size = max(1, min(1000, int(page_size or 200)))
        safe_max = max(1, int(max_items or 5000))
        skip = 0
        yielded = 0
        total: int | None = None
        while yielded < safe_max:
            page = self.list_project_work_packages_page(
                project_ref,
                skip=skip,
                limit=min(safe_page_size, safe_max - yielded),
            )
            items = list(page.get("items") or [])
            if total is None:
                try:
                    total = int(page.get("total") or 0)
                except Exception:
                    total = None
            if not items:
                break
            for item in items:
                if yielded >= safe_max:
                    break
                yielded += 1
                yield item
            skip += len(items)
            if len(items) < safe_page_size:
                break
            if total is not None and skip >= total:
                break
