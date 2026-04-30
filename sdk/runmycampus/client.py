"""
Minimal API client for RunMyCampus. Uses requests; auth via session cookies or future API token.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import requests
    from requests.exceptions import RequestException
except ImportError:
    requests = None  # type: ignore[assignment]
    RequestException = OSError  # type: ignore[misc,assignment]


def _should_retry_status(status: int | None) -> bool:
    if status is None:
        return True
    return status == 429 or status >= 500


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

    def request_with_retries(
        self,
        method: str,
        path: str,
        *,
        max_attempts: int = 4,
        backoff_seconds: tuple[float, ...] = (0.25, 1.0, 3.0),
        **kwargs: Any,
    ) -> Any:
        """
        Perform GET/POST with exponential backoff on 429 / 5xx / connection errors.
        """
        import time

        for attempt in range(max_attempts):
            try:
                fn = getattr(self.session, method.lower(), None)
                if fn is None:
                    raise ValueError(f"Unsupported method {method}")
                url = (
                    self.base_url + path
                    if path.startswith("/")
                    else f"{self.base_url}/{path}"
                )
                resp = fn(url, **kwargs)
                if hasattr(resp, "status_code") and _should_retry_status(
                    resp.status_code
                ):
                    if attempt < max_attempts - 1:
                        delay = backoff_seconds[
                            min(attempt, len(backoff_seconds) - 1)
                        ]
                        time.sleep(delay)
                        continue
                return resp
            except RequestException:
                if attempt < max_attempts - 1:
                    delay = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError("request_with_retries exhausted without response")
