//! Tauri sibling library entry (v3.37.0 Agent 4).
//!
//! Exposes the RMC platform handshake + canonical-CSV ingest modules
//! plus four Tauri commands wired by `main.rs`:
//!
//!   * `rmc_login(server_url, email, password)`
//!   * `rmc_fetch_maa(server_url, tenant_slug, vendor, version)`
//!   * `rmc_sign_maa(server_url, tenant_slug, vendor, holder, role,
//!                    agreement_version, body)`
//!   * `rmc_ingest_csv(server_url, tenant_slug, csv_path, vendor_source,
//!                     pubkey_b64, maa_id, idempotency_key)`
//!
//! The bearer token returned by `rmc_login` is held only inside the
//! frontend's session memory; we never persist it. The frontend
//! passes it back on every subsequent command.

pub mod canonical_csv;
pub mod extractors; // honest-stub placeholder per architectural boundary.
pub mod rmc_handshake;

use crate::canonical_csv::{
    canonicalize_row, match_canonical_domain, parse_csv, seal_box_and_upload, CanonicalRow,
};
use crate::rmc_handshake::{
    fetch_maa_text, login, sign_and_submit_maa, Credentials, MaaText, MAAReceipt, SessionToken,
};
use std::path::PathBuf;

#[derive(serde::Serialize)]
pub struct LoginResultDTO {
    pub bearer: String,
}

#[derive(serde::Serialize)]
pub struct IngestResultDTO {
    pub receipt_id: i64,
    pub bundle_id: Option<i64>,
    pub status: String,
    pub canonical_sha256: String,
    pub matched_domain: String,
    pub row_count: usize,
}

#[tauri::command]
pub async fn rmc_login(
    server_url: String,
    email: String,
    password: String,
) -> Result<LoginResultDTO, String> {
    let creds = Credentials { email, password };
    let token: SessionToken = login(&server_url, creds)
        .await
        .map_err(|e| e.to_string())?;
    Ok(LoginResultDTO {
        bearer: token.bearer.clone(),
    })
}

#[tauri::command]
pub async fn rmc_fetch_maa(
    server_url: String,
    bearer: String,
    tenant_slug: String,
    vendor: String,
    version: Option<String>,
) -> Result<MaaText, String> {
    let token = SessionToken::new(bearer);
    fetch_maa_text(&server_url, &token, &tenant_slug, &vendor, version.as_deref())
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn rmc_sign_maa(
    server_url: String,
    bearer: String,
    tenant_slug: String,
    vendor: String,
    holder: String,
    role: String,
    agreement_version: String,
    body: String,
) -> Result<MAAReceipt, String> {
    let token = SessionToken::new(bearer);
    sign_and_submit_maa(
        &server_url,
        &token,
        &tenant_slug,
        &vendor,
        &holder,
        &role,
        &agreement_version,
        &body,
    )
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn rmc_ingest_csv(
    server_url: String,
    bearer: String,
    csv_path: String,
    vendor_source: String,
    pubkey_b64: String,
    maa_id: i64,
    idempotency_key: String,
) -> Result<IngestResultDTO, String> {
    let path = PathBuf::from(&csv_path);
    let (headers, raw_rows) = parse_csv(&path).map_err(|e| e.to_string())?;
    let domain = match_canonical_domain(&headers).ok_or_else(|| {
        "csv headers do not match any canonical domain (try renaming columns to canonical names)"
            .to_string()
    })?;
    let canonical_rows: Vec<CanonicalRow> = raw_rows
        .iter()
        .map(|r| canonicalize_row(r, &domain))
        .collect();
    let receipt = seal_box_and_upload(
        &canonical_rows,
        &domain,
        &pubkey_b64,
        &server_url,
        &bearer,
        maa_id,
        &vendor_source,
        &idempotency_key,
    )
    .await
    .map_err(|e| e.to_string())?;
    Ok(IngestResultDTO {
        receipt_id: receipt.receipt_id,
        bundle_id: receipt.bundle_id,
        status: receipt.status,
        canonical_sha256: receipt.canonical_sha256,
        matched_domain: domain.0,
        row_count: canonical_rows.len(),
    })
}

/// Field Client offline vault — Stronghold integration stub (SODP batch 1409).
/// Production builds wire `tauri-plugin-stronghold`; this stub keeps `cargo check` green.
#[tauri::command]
pub fn rmc_stronghold_seal(_pin: String, _payload_b64: String) -> Result<String, String> {
    Err("stronghold_plugin_not_linked — use WebCrypto vault in PWA or enable Stronghold in release build".into())
}

#[tauri::command]
pub fn rmc_stronghold_open(_pin: String, _sealed_id: String) -> Result<String, String> {
    Err("stronghold_plugin_not_linked".into())
}
