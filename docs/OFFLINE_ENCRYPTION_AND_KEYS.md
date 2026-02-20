# Offline Queue and Draft Encryption

The service worker and form-draft-save support optional encryption of queued payloads and drafts so that sensitive data is not stored in plaintext in IndexedDB or localStorage.

## Current hooks

- **Service worker** ([static/js/service-worker.js](static/js/service-worker.js)): `maybeEncryptBody(body)` and `maybeDecryptBody(body)` are called when storing and reading queue items. When `OFFLINE_CONFIG.enableQueueEncryption` is true and `OFFLINE_CONFIG.queueEncryptionKey` is set, the body is encoded (currently base64); for production you should use Web Crypto API (AES-GCM) with a proper key.
- **Config**: Pass `enableQueueEncryption` and `queueEncryptionKey` via `SET_OFFLINE_CONFIG` from the page (e.g. from `SMS_OFFLINE_CONFIG` in [templates/portal_base.html](templates/portal_base.html)). Do **not** hardcode the key in the template; obtain it from the server after login (e.g. a short-lived token or a user-derived key).
- **Form drafts** ([static/js/form-draft-save.js](static/js/form-draft-save.js)): Drafts and pending submissions are stored in localStorage. To encrypt, wrap `localStorage.setItem`/`getItem` for keys like `sms_draft_*` and `sms_pending_mark_submissions` with your encrypt/decrypt functions using the same key source.

## Key storage and rotation

- **Key source**: Prefer a key returned by the server after authentication (e.g. `GET /api/sync/encryption-key/` returning a short-lived value) or derived from the user password/session (e.g. PBKDF2 or Web Crypto `subtle.importKey`). Store the key in memory only (variable in the page), not in localStorage, so that closing the tab invalidates it; the next login fetches a new key.
- **Rotation**: When the server rotates the key, return a new key and optionally a version; the client can re-encrypt existing queue items on next load or leave old items to be replayed and then cleared. Document your rotation policy (e.g. per-session, daily, or on password change).

## Implementing production encryption

1. In the service worker, replace the current base64 encode/decode in `maybeEncryptBody`/`maybeDecryptBody` with AES-GCM (Web Crypto API). Use a key passed from the page via `SET_OFFLINE_CONFIG.payload.queueEncryptionKey` (as a CryptoKey object or raw key material).
2. On the Django side, add an endpoint that returns an encryption key or salt for the current user (e.g. after login) and include it in the initial config or fetch it from the portal page.
3. In form-draft-save, encrypt draft and pending values before `setItem` and decrypt after `getItem` using the same key or a dedicated draft key.

See [docs/OFFLINE_MODE_AUDIT.md](OFFLINE_MODE_AUDIT.md) for the original hook references.
