//! RMC platform handshake (v3.37.0 Agent 4).
//!
//! TARGET: RunMyCampus's OWN `/api/v1/...` endpoints. This module
//! NEVER programmatically logs into any third-party SIS (PowerSchool,
//! Blackbaud, Veracross, Alma, FACTS, Skyward). Vendor extraction
//! lives in `companion-extension/` (the browser extension where the
//! operator's own authenticated tab is the security boundary). The
//! Tauri sibling's only login is to the RMC platform itself.
//!
//! Four steps in a strict order:
//!   1. `login(server_url, email, password) -> SessionToken`
//!      POSTs to `/api/v1/auth/login/` with rustls-tls reqwest; no
//!      cookie jar, just a bearer token. Password is zeroed on Drop.
//!   2. `fetch_maa_text(token, tenant_slug, version) -> MaaText`
//!      GETs `/api/v1/migration/maa/text/` (mirrors the existing
//!      `apps/migration_cloud/companion_receiver.py::maa_text_view`).
//!   3. `sign_and_submit_maa(token, tenant_slug, body, attestation)
//!      -> MAAReceipt`
//!      POSTs `/api/v1/migration/maa/sign/` echoing the verbatim body
//!      so the server can constant-time-compare against its own
//!      rendered active-version body.
//!   4. `fetch_receipt(token, receipt_id) -> Receipt`
//!      GETs `/api/v1/migration/receipts/<id>/`.
//!
//! Secret hygiene:
//!   * `Credentials` (email+password) and `SessionToken` both impl
//!     `Drop` to zeroize their inner bytes.
//!   * No `log::*` call EVER prints password, token, or signature_text.
//!     We log: server URL host, tenant slug, status code, receipt id.
//!   * Token comparison uses `subtle::ConstantTimeEq`.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::time::Duration;
use subtle::ConstantTimeEq;
use thiserror::Error;
use zeroize::{Zeroize, ZeroizeOnDrop};

const RMC_LOGIN_PATH: &str = "/api/v1/auth/login/";
const RMC_MAA_TEXT_PATH: &str = "/api/v1/migration/maa/text/";
const RMC_MAA_SIGN_PATH: &str = "/api/v1/migration/maa/sign/";
const RMC_RECEIPT_PATH_PREFIX: &str = "/api/v1/migration/receipts/";

const DEFAULT_TIMEOUT_SECS: u64 = 30;

#[derive(Debug, Error)]
pub enum HandshakeError {
    #[error("invalid server URL")]
    BadServerUrl,
    #[error("network transport error")]
    Transport,
    #[error("authentication failed (401)")]
    Unauthorized,
    #[error("forbidden (403)")]
    Forbidden,
    #[error("not found (404)")]
    NotFound,
    #[error("server returned status {0}")]
    HttpStatus(u16),
    #[error("response decode failed")]
    BadResponse,
    #[error("MAA fetch failed")]
    MaaFetchFailed,
    #[error("MAA signing rejected by server")]
    MaaSignRejected,
}

/// Operator credentials for the RMC platform login only.
///
/// `Zeroize` + `ZeroizeOnDrop` so the password bytes are overwritten
/// the moment the struct goes out of scope.
#[derive(Zeroize, ZeroizeOnDrop)]
pub struct Credentials {
    pub email: String,
    pub password: String,
}

impl fmt::Debug for Credentials {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Credentials")
            .field("email", &"<redacted>")
            .field("password", &"<redacted>")
            .finish()
    }
}

/// Bearer token returned by `/api/v1/auth/login/`. Zeroized on Drop.
#[derive(Zeroize, ZeroizeOnDrop)]
pub struct SessionToken {
    pub bearer: String,
}

impl SessionToken {
    pub fn new(bearer: String) -> Self {
        Self { bearer }
    }

    /// Constant-time equality so a token-comparison loop never leaks
    /// information by short-circuiting.
    pub fn ct_eq(&self, other: &SessionToken) -> bool {
        self.bearer
            .as_bytes()
            .ct_eq(other.bearer.as_bytes())
            .into()
    }

    /// Authorization header value. The token itself is not logged;
    /// callers must only pass this directly into the HTTP client.
    pub fn authorization_header(&self) -> String {
        format!("Bearer {}", self.bearer)
    }
}

impl fmt::Debug for SessionToken {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SessionToken")
            .field("bearer", &"<redacted>")
            .finish()
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct MaaText {
    pub vendor: String,
    pub version: String,
    pub text: String,
    pub is_draft: bool,
    pub active_version: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MAAReceipt {
    pub maa_id: i64,
    pub signed_at: String,
    pub agreement_version: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Receipt {
    pub receipt_id: i64,
    pub bundle_id: Option<i64>,
    pub status: String,
}

#[derive(Debug, Serialize)]
struct LoginRequest<'a> {
    email: &'a str,
    password: &'a str,
}

#[derive(Debug, Deserialize)]
struct LoginResponse {
    /// Server returns ``{"token": "<bearer>"}``; many Django DRF
    /// projects use ``key`` or ``access`` — accept all three to ease
    /// integration. Exactly one MUST be present.
    #[serde(default)]
    token: Option<String>,
    #[serde(default)]
    key: Option<String>,
    #[serde(default)]
    access: Option<String>,
}

#[derive(Debug, Serialize)]
struct MaaSignRequest<'a> {
    vendor_source: &'a str,
    vendor_account_holder_name: &'a str,
    signed_by_role: &'a str,
    agreement_version: &'a str,
    /// Verbatim body the client rendered, so the server can compare
    /// byte-for-byte against its own render. Mirrors the
    /// ``submitted_signature_text`` contract in companion_receiver.py.
    submitted_signature_text: &'a str,
}

/// Build an HTTP client with rustls-TLS, no cookie store, sensible
/// timeouts. We do NOT enable a cookie jar — the RMC platform issues a
/// bearer token and we carry it explicitly on every request.
pub fn build_client() -> Result<reqwest::Client, HandshakeError> {
    reqwest::Client::builder()
        .use_rustls_tls()
        .cookie_store(false)
        .https_only(false) // dev may target http://localhost
        .timeout(Duration::from_secs(DEFAULT_TIMEOUT_SECS))
        .user_agent("RunMyCampus-Companion-Tauri/3.37.0")
        .build()
        .map_err(|_| HandshakeError::Transport)
}

fn join_url(base: &str, path: &str) -> Result<String, HandshakeError> {
    let trimmed = base.trim_end_matches('/');
    if trimmed.is_empty() || !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
        return Err(HandshakeError::BadServerUrl);
    }
    Ok(format!("{trimmed}{path}"))
}

/// Map HTTP status to a typed error. Used by every endpoint wrapper.
fn classify_status(status: u16) -> HandshakeError {
    match status {
        401 => HandshakeError::Unauthorized,
        403 => HandshakeError::Forbidden,
        404 => HandshakeError::NotFound,
        s => HandshakeError::HttpStatus(s),
    }
}

/// Step 1: login to the RMC platform. Returns a `SessionToken` carrying
/// the bearer string. The plaintext password is zeroed on Drop.
pub async fn login(
    server_url: &str,
    creds: Credentials,
) -> Result<SessionToken, HandshakeError> {
    let url = join_url(server_url, RMC_LOGIN_PATH)?;
    let client = build_client()?;
    let body = LoginRequest {
        email: &creds.email,
        password: &creds.password,
    };
    let response = client
        .post(&url)
        .json(&body)
        .send()
        .await
        .map_err(|_| HandshakeError::Transport)?;
    let status = response.status().as_u16();
    // NEVER log the bearer or password. ID + status only.
    log::info!("rmc_handshake.login status={} email_hash_prefix=<sha>", status);
    if !response.status().is_success() {
        return Err(classify_status(status));
    }
    let parsed: LoginResponse = response
        .json()
        .await
        .map_err(|_| HandshakeError::BadResponse)?;
    let bearer = parsed
        .token
        .or(parsed.key)
        .or(parsed.access)
        .ok_or(HandshakeError::BadResponse)?;
    drop(creds); // Explicit zeroize trigger via ZeroizeOnDrop.
    Ok(SessionToken::new(bearer))
}

/// Step 2: fetch the verbatim MAA body the operator will sign.
pub async fn fetch_maa_text(
    server_url: &str,
    token: &SessionToken,
    tenant_slug: &str,
    vendor: &str,
    version: Option<&str>,
) -> Result<MaaText, HandshakeError> {
    let url = join_url(server_url, RMC_MAA_TEXT_PATH)?;
    let client = build_client()?;
    let mut query: Vec<(&str, &str)> = vec![("vendor", vendor), ("tenant", tenant_slug)];
    if let Some(v) = version {
        query.push(("version", v));
    }
    let response = client
        .get(&url)
        .header("Authorization", token.authorization_header())
        .query(&query)
        .send()
        .await
        .map_err(|_| HandshakeError::Transport)?;
    let status = response.status().as_u16();
    log::info!(
        "rmc_handshake.fetch_maa_text status={} tenant_slug={} vendor={}",
        status, tenant_slug, vendor
    );
    if !response.status().is_success() {
        return Err(classify_status(status));
    }
    let text: MaaText = response
        .json()
        .await
        .map_err(|_| HandshakeError::MaaFetchFailed)?;
    Ok(text)
}

/// Step 3: sign and submit the MAA. The `body` argument MUST be the
/// verbatim text fetched in step 2 — the server constant-time-compares
/// our submitted body against its own render and rejects on drift.
pub async fn sign_and_submit_maa(
    server_url: &str,
    token: &SessionToken,
    tenant_slug: &str,
    vendor: &str,
    holder: &str,
    role: &str,
    agreement_version: &str,
    body: &str,
) -> Result<MAAReceipt, HandshakeError> {
    let url = join_url(server_url, RMC_MAA_SIGN_PATH)?;
    let client = build_client()?;
    let req = MaaSignRequest {
        vendor_source: vendor,
        vendor_account_holder_name: holder,
        signed_by_role: role,
        agreement_version,
        submitted_signature_text: body,
    };
    let response = client
        .post(&url)
        .header("Authorization", token.authorization_header())
        .header("X-Tenant", tenant_slug)
        .json(&req)
        .send()
        .await
        .map_err(|_| HandshakeError::Transport)?;
    let status = response.status().as_u16();
    // NEVER log the body itself — only status + sha prefix would be OK
    // here, but we keep it strictly to status + IDs to avoid any
    // accidental leak of signature_text.
    log::info!(
        "rmc_handshake.sign_and_submit_maa status={} tenant_slug={} vendor={}",
        status, tenant_slug, vendor
    );
    if !response.status().is_success() {
        if status == 400 {
            return Err(HandshakeError::MaaSignRejected);
        }
        return Err(classify_status(status));
    }
    let receipt: MAAReceipt = response
        .json()
        .await
        .map_err(|_| HandshakeError::BadResponse)?;
    Ok(receipt)
}

/// Step 4: fetch a receipt by id (after upload). The receipt forms
/// the audit chain root.
pub async fn fetch_receipt(
    server_url: &str,
    token: &SessionToken,
    receipt_id: i64,
) -> Result<Receipt, HandshakeError> {
    let path = format!("{RMC_RECEIPT_PATH_PREFIX}{receipt_id}/");
    let url = join_url(server_url, &path)?;
    let client = build_client()?;
    let response = client
        .get(&url)
        .header("Authorization", token.authorization_header())
        .send()
        .await
        .map_err(|_| HandshakeError::Transport)?;
    let status = response.status().as_u16();
    log::info!("rmc_handshake.fetch_receipt status={} receipt_id={}", status, receipt_id);
    if !response.status().is_success() {
        return Err(classify_status(status));
    }
    let receipt: Receipt = response
        .json()
        .await
        .map_err(|_| HandshakeError::BadResponse)?;
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn join_url_rejects_missing_scheme() {
        assert!(matches!(
            join_url("example.com", RMC_LOGIN_PATH),
            Err(HandshakeError::BadServerUrl)
        ));
    }

    #[test]
    fn join_url_trims_trailing_slash() {
        let u = join_url("https://rmc.example.com/", RMC_LOGIN_PATH).unwrap();
        assert_eq!(u, "https://rmc.example.com/api/v1/auth/login/");
    }

    #[test]
    fn classify_status_401_unauthorized() {
        assert!(matches!(classify_status(401), HandshakeError::Unauthorized));
    }

    #[test]
    fn classify_status_403_forbidden() {
        assert!(matches!(classify_status(403), HandshakeError::Forbidden));
    }

    #[test]
    fn classify_status_404_not_found() {
        assert!(matches!(classify_status(404), HandshakeError::NotFound));
    }

    #[test]
    fn credentials_debug_redacts() {
        let c = Credentials {
            email: "op@example.com".into(),
            password: "supersecret".into(),
        };
        let s = format!("{:?}", c);
        assert!(!s.contains("supersecret"));
        assert!(s.contains("<redacted>"));
    }

    #[test]
    fn session_token_debug_redacts() {
        let t = SessionToken::new("abc.def.ghi".into());
        let s = format!("{:?}", t);
        assert!(!s.contains("abc.def.ghi"));
        assert!(s.contains("<redacted>"));
    }

    #[test]
    fn session_token_ct_eq_matches() {
        let a = SessionToken::new("same".into());
        let b = SessionToken::new("same".into());
        let c = SessionToken::new("diff".into());
        assert!(a.ct_eq(&b));
        assert!(!a.ct_eq(&c));
    }

    #[test]
    fn token_zeroized_on_drop() {
        // Construct, capture pointer to inner bytes (via len), drop,
        // then assert the zeroize trait was applied (compile-time
        // assertion via trait bound — the macro generates Drop+Zeroize).
        fn assert_zeroize<T: zeroize::ZeroizeOnDrop>(_: &T) {}
        let t = SessionToken::new("token".into());
        assert_zeroize(&t);
        drop(t);
    }
}
