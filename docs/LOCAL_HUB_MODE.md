# Local Hub Mode (Resilient Edge)

In environments with no internet but a working local Wi-Fi, one device can run the school management system and act as the **local server**; other devices connect to it over the LAN.

## Concept

- **Hub device**: A Raspberry Pi, laptop, or desktop on the same Wi-Fi runs the Django app (and optionally a reverse proxy). It is reachable at e.g. `http://192.168.1.100:8000/` or `http://sms-hub.local/`.
- **Client devices**: Tablets and phones point their browser (or PWA) to the hub’s URL. They use the same portal, API, and offline behaviour; when the hub is the only “internet,” all traffic goes to it.

## Deployment (outline)

1. **Install on the hub**: Clone the project, install dependencies, run migrations, create a superuser. Use a process manager (e.g. systemd or supervisor) to run `gunicorn` or `runserver` bound to `0.0.0.0` so the app is reachable from other devices on the LAN.
2. **Network**: Ensure the hub has a fixed IP (DHCP reservation or static) and that firewall allows HTTP/HTTPS to the app port.
3. **Client configuration**: On each client device, open the hub URL (e.g. `http://192.168.1.100:8000/`) and log in. Bookmark or “Add to Home Screen” so the PWA uses that origin. No code change is required if clients always use the hub URL.
4. **Optional fallback in the app**: If you normally use a cloud URL but want clients to fall back to a hub when the cloud is unreachable, add a configurable **hub base URL** (e.g. in Site Settings or `SMS_OFFLINE_CONFIG.hubBaseUrl`). In the service worker fetch handler, when a request to the main origin fails (network error), retry with `hubBaseUrl` + same path. This requires CORS and cookies to be valid for the hub origin (same-site or configured accordingly).

## Security and data

- The hub holds a copy of the database; restrict physical and network access.
- Use HTTPS on the hub if possible (e.g. self-signed cert or LAN-only CA). For HTTP-only setups, use only on trusted networks.
- Back up the hub’s database regularly; when internet returns, you can sync data to the central server if a sync mechanism is implemented.

## Summary

- **No code change required** for “everyone uses the hub URL” deployment.
- **Optional**: Add `hubBaseUrl` and service worker retry-to-hub logic for “prefer cloud, fallback to hub” behaviour. Document the exact fetch fallback and cookie/origin behaviour when you implement it.
