# RunMyCampus SDK (stub)

Minimal client surface for RunMyCampus API integration: auth helper and API client stub. Full SDK is product/roadmap; this package provides a documentable placeholder and minimal usage.

## Install

From repo root (or once published):

```bash
pip install -e ./sdk
```

## Usage

```python
from runmycampus import RunMyCampusClient

# Base URL is your school subdomain (e.g. https://yourschool.runmycampus.com)
client = RunMyCampusClient(base_url="https://yourschool.runmycampus.com")
# Auth: use session cookie after login, or API token when supported
# client.session.auth = ("token", "your-api-token")

# Stub: get API schema or interop readiness
# response = client.get("/api/schema/")
# response = client.get("/api/interop/oneroster/")
```

## Auth

- **Session:** After logging in via the web UI, use the same session (e.g. `requests.Session()` with cookies) for API calls when using cookie-based auth.
- **API token:** When the platform supports API tokens, set `client.session.headers["Authorization"] = "Bearer <token>"` or use the auth helper in this package.

## Links

- Developer portal: `/developer-portal/`
- API schema (in-app): `/api/schema/ui/`
- Interop: `/api/interop/oneroster/`, `/api/interop/lti13/`, `/api/interop/edfi/`, `/api/interop/ceds/`
