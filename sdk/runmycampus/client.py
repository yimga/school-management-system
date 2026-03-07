"""
Minimal API client for RunMyCampus. Uses requests; auth via session cookies or future API token.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class RunMyCampusClient:
    """
    Stub client for RunMyCampus API. Base URL should be the school subdomain
    (e.g. https://yourschool.runmycampus.com).
    """

    def __init__(self, base_url: str, session: Optional[Any] = None):
        self.base_url = base_url.rstrip("/")
        if requests is None:
            raise ImportError("RunMyCampus SDK requires 'requests'. pip install requests")
        self.session = session if session is not None else requests.Session()
        self.session.headers.setdefault("Accept", "application/json")

    def get(self, path: str, **kwargs: Any) -> Any:
        """GET path relative to base_url (e.g. /api/schema/)."""
        url = self.base_url + path if path.startswith("/") else f"{self.base_url}/{path}"
        return self.session.get(url, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """POST path relative to base_url."""
        url = self.base_url + path if path.startswith("/") else f"{self.base_url}/{path}"
        return self.session.post(url, **kwargs)

    def set_bearer_token(self, token: str) -> None:
        """Set Authorization: Bearer <token> for API token auth (when supported)."""
        self.session.headers["Authorization"] = f"Bearer {token}"
