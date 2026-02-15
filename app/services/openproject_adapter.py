from __future__ import annotations

from typing import Any

import requests


class OpenProjectAdapter:
    def __init__(self, *, base_url: str, api_token: str) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.api_token = str(api_token or "").strip()
        if not self.base_url:
            raise RuntimeError("OPENPROJECT_BASE_URL is empty.")
        if not self.api_token:
            raise RuntimeError("OPENPROJECT_API_TOKEN is empty.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def ping(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/v3"
        response = requests.get(url, headers=self._headers(), timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"OpenProject API ping failed: HTTP {response.status_code} {response.text}")
        return response.json()

    def attach_external_link(
        self,
        *,
        work_package_id: int,
        title: str,
        url: str,
    ) -> dict[str, Any]:
        # OpenProject API does not have a fully stable generic endpoint for "external URL attachment"
        # across editions. This method stores the integration action as a note in the work package.
        endpoint = f"{self.base_url}/api/v3/work_packages/{int(work_package_id)}"
        patch_payload = {
            "_links": {},
            "description": {
                "format": "markdown",
                "raw": f"{title}\n\n{url}",
            },
        }
        response = requests.patch(endpoint, headers=self._headers(), json=patch_payload, timeout=25)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenProject sync failed for work package {work_package_id}: "
                f"HTTP {response.status_code} {response.text}"
            )
        return response.json()
