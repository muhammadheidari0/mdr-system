from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


class GoogleOAuthAdapter:
    def __init__(
        self,
        *,
        oauth_client_id: str,
        oauth_client_secret: str,
        oauth_refresh_token: str,
        sender_email: str = "",
        calendar_id: str = "",
        token_uri: str = "https://oauth2.googleapis.com/token",
        connect_timeout: float = 5,
        read_timeout: float = 10,
    ) -> None:
        self.oauth_client_id = str(oauth_client_id or "").strip()
        self.oauth_client_secret = str(oauth_client_secret or "").strip()
        self.oauth_refresh_token = str(oauth_refresh_token or "").strip()
        self.sender_email = str(sender_email or "").strip()
        self.calendar_id = str(calendar_id or "").strip()
        self.token_uri = str(token_uri or "").strip() or "https://oauth2.googleapis.com/token"
        self.timeout = (float(connect_timeout), float(read_timeout))

    def _require_oauth_credentials(self) -> None:
        if not self.oauth_client_id:
            raise RuntimeError("Google OAuth client_id is required.")
        if not self.oauth_client_secret:
            raise RuntimeError("Google OAuth client_secret is required.")
        if not self.oauth_refresh_token:
            raise RuntimeError("Google OAuth refresh_token is required.")

    def _refresh_access_token(self) -> str:
        self._require_oauth_credentials()
        response = requests.post(
            self.token_uri,
            data={
                "client_id": self.oauth_client_id,
                "client_secret": self.oauth_client_secret,
                "refresh_token": self.oauth_refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Google OAuth token refresh failed: HTTP {response.status_code}")
        payload = response.json() if response.content else {}
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Google OAuth token refresh did not return access_token.")
        return access_token

    def _authorized_get(self, url: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        token = self._refresh_access_token()
        return requests.get(
            str(url or "").strip(),
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params or {},
            timeout=self.timeout,
        )

    def ping(self, service: str) -> dict[str, Any]:
        key = str(service or "").strip().lower()
        if key not in {"drive", "gmail", "calendar"}:
            raise RuntimeError("Google ping service must be one of drive, gmail, calendar.")

        if key == "drive":
            url = "https://www.googleapis.com/drive/v3/about"
            params = {"fields": "user(displayName,emailAddress)"}
            missing_message = ""
        elif key == "gmail":
            user_ref = quote(self.sender_email, safe="") if self.sender_email else "me"
            url = f"https://gmail.googleapis.com/gmail/v1/users/{user_ref}/profile"
            params = {}
            missing_message = "sender_email is recommended for Gmail ping."
        else:
            if self.calendar_id:
                calendar_ref = quote(self.calendar_id, safe="")
                url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_ref}"
                params = {}
            else:
                url = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
                params = {"maxResults": 1}
            missing_message = "calendar_id is optional for calendar ping."

        try:
            response = self._authorized_get(url, params=params)
        except requests.Timeout:
            return {
                "service": key,
                "reachable": False,
                "auth_ok": False,
                "status_code": None,
                "message": "Google ping timed out.",
            }
        except requests.RequestException:
            return {
                "service": key,
                "reachable": False,
                "auth_ok": False,
                "status_code": None,
                "message": "Google service is unreachable (network/TLS error).",
            }

        status_code = int(response.status_code)
        reachable = True
        auth_ok = status_code < 400
        if status_code in {401, 403}:
            auth_ok = False
            message = f"Google {key} is reachable, but authentication/permission failed."
        elif status_code == 404:
            auth_ok = False
            message = f"Google {key} endpoint not found or resource not visible."
        elif status_code >= 400:
            auth_ok = False
            message = f"Google {key} returned HTTP {status_code}."
        else:
            suffix = f" {missing_message}" if missing_message else ""
            message = f"Google {key} reachable and authenticated.{suffix}".strip()
        return {
            "service": key,
            "reachable": reachable,
            "auth_ok": auth_ok,
            "status_code": status_code,
            "message": message,
        }
