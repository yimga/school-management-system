//! Canonical-CSV ingest (v3.37.0 Agent 4).
//!
//! Operator's manual SIS-export flow:
//!   1. Operator opens their SIS (PowerSchool, Blackbaud, Veracross,
//!      Alma, FACTS, Skyward) in THEIR OWN browser tab, signs in
//!      with their own credentials, uses the SIS's own export UI
//!      (every supported SIS ships a CSV export action) to save a
//!      CSV file to disk.
//!   2. Operator drops the CSV into the Tauri appliance.
//!   3. This module parses + matches against canonical headers +
//!      seals + uploads. We do NOT log into the SIS, do NOT replay
//!      sessions, do NOT capture cookies — the CSV file is the
//!      handoff boundary.
//!
//! Sealed-box semantics mirror `companion-extension/src/lib/crypto.ts`:
//! libsodium `crypto_box_seal` over the recipient's X25519 public key.

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::Path;
use thiserror::Error;

use crate::extractors;

/// Embedded canonical-header map. Mirror of
/// `apps/migration_cloud/accelerators/runmycampus_canonical.py::DOMAIN_CANONICAL_HEADERS`.
/// Loaded once at module init from the bundled JSON file.
const CANONICAL_HEADERS_JSON: &str = include_str!("canonical_headers.json");

/// Minimum overlap between input headers and a canonical domain header
/// set to count as a match. Mirrors HEADER_MATCH_MIN_HITS = 3 from the
/// Django accelerator.
const HEADER_MATCH_MIN_HITS: usize = 3;

#[derive(Debug, Error)]
pub enum CsvError {
    #[error("CSV file not found")]
    NotFound,
    #[error("CSV parse failed")]
    ParseFailed,
    #[error("canonical-header table unparseable (bundled JSON corrupt)")]
    CanonicalTableCorrupt,
    #[error("sealed-box encryption failed")]
    SealFailed,
    #[error("invalid server public key (must be 32 bytes base64)")]
    BadPubkey,
    #[error("network transport error")]
    Transport,
    #[error("upload rejected status={0}")]
    UploadRejected(u16),
}

/// A canonical "domain" (e.g. "students", "guardians", "attendance").
/// Wraps a String for typed clarity at API boundaries.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CanonicalDomain(pub String);

#[derive(Debug, Clone)]
pub struct CanonicalRow {
    /// Cell values keyed by canonical header. Unknown vendor columns
    /// are preserved verbatim under their original header name (so the
    /// server's mapper can still consume them as `custom_fields`).
    pub fields: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UploadReceipt {
    pub receipt_id: i64,
    pub bundle_id: Option<i64>,
    pub status: String,
    /// SHA-256 of the canonical-bytes input (NOT the sealed
    /// ciphertext). Two re-uploads of identical canonical rows will
    /// produce the same `canonical_sha256` even though sealed-box
    /// ciphertexts differ each time (random nonce).
    pub canonical_sha256: String,
}

/// Load the canonical header table. Public so tests can verify the
/// bundled JSON parses to ≥ 20 domains.
pub fn load_canonical_headers() -> Result<HashMap<String, Vec<String>>, CsvError> {
    let parsed: HashMap<String, serde_json::Value> = serde_json::from_str(CANONICAL_HEADERS_JSON)
        .map_err(|_| CsvError::CanonicalTableCorrupt)?;
    let mut out: HashMap<String, Vec<String>> = HashMap::new();
    for (k, v) in parsed.into_iter() {
        if k.starts_with('_') {
            continue; // skip "_comment"
        }
        let arr = v.as_array().ok_or(CsvError::CanonicalTableCorrupt)?;
        let mut headers: Vec<String> = Vec::with_capacity(arr.len());
        for item in arr {
            let s = item.as_str().ok_or(CsvError::CanonicalTableCorrupt)?;
            headers.push(s.to_string());
        }
        out.insert(k, headers);
    }
    Ok(out)
}

/// Parse a CSV file into a (headers, rows) pair. `rows` is a Vec of
/// HashMap from header → cell value.
pub fn parse_csv(path: &Path) -> Result<(Vec<String>, Vec<HashMap<String, String>>), CsvError> {
    if !path.exists() {
        return Err(CsvError::NotFound);
    }
    let mut rdr = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_path(path)
        .map_err(|_| CsvError::ParseFailed)?;
    let headers: Vec<String> = rdr
        .headers()
        .map_err(|_| CsvError::ParseFailed)?
        .iter()
        .map(|h| h.trim().to_string())
        .collect();
    let mut rows: Vec<HashMap<String, String>> = Vec::new();
    for result in rdr.records() {
        let record = result.map_err(|_| CsvError::ParseFailed)?;
        let mut row = HashMap::new();
        for (i, cell) in record.iter().enumerate() {
            if let Some(h) = headers.get(i) {
                row.insert(h.clone(), cell.to_string());
            }
        }
        rows.push(row);
    }
    Ok((headers, rows))
}

/// Parse a CSV file AND apply vendor pre-processing in one step.
///
/// Pipeline:
///   1. `parse_csv()` → (headers, raw rows).
///   2. `extractors::detect_vendor()` → optional vendor name from the
///      header signature.
///   3. `extractors::preprocess_for_vendor()` → vendor-specific
///      normalization (date format, header casing, status codes,
///      role partitioning, JSON-in-cell). Unknown vendor → identity.
///
/// The output is a `(detected_vendor, normalized_headers, rows)`
/// triple. Downstream callers continue with
/// `match_canonical_domain()` + `canonicalize_row()`.
pub fn parse_and_preprocess(
    path: &Path,
) -> Result<(Option<&'static str>, Vec<String>, Vec<HashMap<String, String>>), CsvError> {
    let (headers, rows) = parse_csv(path)?;
    let vendor = extractors::detect_vendor(&headers);
    let processed = extractors::preprocess_for_vendor(vendor, rows);
    // Recompute headers from the union of keys in processed rows
    // (some vendor extractors split/rename columns).
    let mut header_set: std::collections::BTreeSet<String> =
        std::collections::BTreeSet::new();
    for r in &processed {
        for k in r.keys() {
            header_set.insert(k.clone());
        }
    }
    let new_headers: Vec<String> = header_set.into_iter().collect();
    // When the vendor extractor renames every header, fall back to
    // the union of processed-row keys. When vendor is None, preserve
    // the original headers vector to maintain order semantics for
    // downstream callers that care about column order.
    let final_headers = if vendor.is_some() {
        new_headers
    } else {
        headers
    };
    Ok((vendor, final_headers, processed))
}

/// Header-only domain match. Returns `Some(domain)` when at least
/// `HEADER_MATCH_MIN_HITS` of the input headers overlap with the
/// canonical set for some domain (picking the domain with the
/// highest overlap; ties broken by name for determinism).
pub fn match_canonical_domain(headers: &[String]) -> Option<CanonicalDomain> {
    let table = load_canonical_headers().ok()?;
    let normalized: Vec<String> = headers.iter().map(|h| h.trim().to_lowercase()).collect();

    let mut best: Option<(String, usize)> = None;
    let mut keys: Vec<&String> = table.keys().collect();
    keys.sort(); // deterministic tie-break.
    for domain in keys {
        let canon = &table[domain];
        let canon_lower: Vec<String> = canon.iter().map(|c| c.to_lowercase()).collect();
        let hits = normalized
            .iter()
            .filter(|h| canon_lower.contains(h))
            .count();
        if hits >= HEADER_MATCH_MIN_HITS {
            match &best {
                None => best = Some((domain.clone(), hits)),
                Some((_, prev_hits)) if hits > *prev_hits => {
                    best = Some((domain.clone(), hits))
                }
                _ => {}
            }
        }
    }
    best.map(|(d, _)| CanonicalDomain(d))
}

/// Apply canonical mapping to a single row. Header-match only — cell
/// values pass through verbatim. Unknown headers stay under their
/// original key.
pub fn canonicalize_row(
    row: &HashMap<String, String>,
    _domain: &CanonicalDomain,
) -> CanonicalRow {
    // Header-match only: pass-through. Server-side mapper handles
    // case normalization + custom_fields routing.
    CanonicalRow {
        fields: row.clone(),
    }
}

/// Serialize a list of canonical rows to deterministic bytes. Same
/// rows → same bytes (sorted keys, sorted row order by external_id
/// when present, JSON encoding).
pub fn canonical_serialize(rows: &[CanonicalRow]) -> Vec<u8> {
    let mut as_maps: Vec<HashMap<String, String>> =
        rows.iter().map(|r| r.fields.clone()).collect();
    // Sort rows for determinism — use the first sortable id column we
    // can find so a re-upload of the same input produces identical bytes.
    as_maps.sort_by(|a, b| {
        let id_keys = [
            "external_id",
            "student_external_id",
            "staff_external_id",
            "guardian_external_id",
            "section_external_id",
            "guardian_external_id",
            "recipient_external_id",
            "item_external_id",
            "subject_external_id",
            "reference",
        ];
        for k in id_keys {
            if let (Some(av), Some(bv)) = (a.get(k), b.get(k)) {
                return av.cmp(bv);
            }
        }
        std::cmp::Ordering::Equal
    });
    // Use sorted-key BTreeMap-equivalent serialization via serde_json's
    // sort_keys feature path: serialize each row into a BTreeMap first.
    let normalized: Vec<std::collections::BTreeMap<String, String>> = as_maps
        .into_iter()
        .map(|m| m.into_iter().collect())
        .collect();
    serde_json::to_vec(&normalized).unwrap_or_default()
}

/// Sealed-box encrypt the canonical-rows payload using libsodium
/// crypto_box_seal (X25519 + XSalsa20-Poly1305). Mirrors the JS
/// companion's `sealBox(plaintext, recipientPubKey)`.
pub fn seal_box(plaintext: &[u8], server_pubkey_b64: &str) -> Result<Vec<u8>, CsvError> {
    use sodiumoxide::crypto::box_::curve25519xsalsa20poly1305::PublicKey;
    use sodiumoxide::crypto::sealedbox;

    // Initialize libsodium once. Safe to call repeatedly per docs.
    if sodiumoxide::init().is_err() {
        return Err(CsvError::SealFailed);
    }
    let pubkey_bytes = B64
        .decode(server_pubkey_b64)
        .map_err(|_| CsvError::BadPubkey)?;
    if pubkey_bytes.len() != 32 {
        return Err(CsvError::BadPubkey);
    }
    let mut buf = [0u8; 32];
    buf.copy_from_slice(&pubkey_bytes);
    let pk = PublicKey(buf);
    Ok(sealedbox::seal(plaintext, &pk))
}

/// Seal the canonical-row payload and upload it via the existing
/// companion-receiver multipart endpoint. The token is the bearer
/// from `rmc_handshake::login`.
pub async fn seal_box_and_upload(
    rows: &[CanonicalRow],
    domain: &CanonicalDomain,
    server_pubkey_b64: &str,
    server_url: &str,
    bearer_token: &str,
    maa_id: i64,
    vendor_source: &str,
    idempotency_key: &str,
) -> Result<UploadReceipt, CsvError> {
    let plaintext = canonical_serialize(rows);
    let canonical_sha = {
        let mut h = Sha256::new();
        h.update(&plaintext);
        format!("{:x}", h.finalize())
    };
    let ciphertext = seal_box(&plaintext, server_pubkey_b64)?;
    let ct_sha = {
        let mut h = Sha256::new();
        h.update(&ciphertext);
        format!("{:x}", h.finalize())
    };

    let metadata = serde_json::json!({
        "maa_id": maa_id,
        "client_idempotency_key": idempotency_key,
        "vendor_source": vendor_source,
        "ciphertext_sha256": ct_sha,
        "plaintext_byte_size": plaintext.len(),
        "domain": domain.0,
        "source": "companion-tauri-csv-ingest",
    });

    let client = reqwest::Client::builder()
        .use_rustls_tls()
        .cookie_store(false)
        .build()
        .map_err(|_| CsvError::Transport)?;
    let url = format!(
        "{}/api/v1/migration/companion/upload/",
        server_url.trim_end_matches('/')
    );
    let form = reqwest::multipart::Form::new()
        .text("metadata", metadata.to_string())
        .part(
            "ciphertext",
            reqwest::multipart::Part::bytes(ciphertext)
                .file_name("companion.bin")
                .mime_str("application/octet-stream")
                .map_err(|_| CsvError::Transport)?,
        );

    let response = client
        .post(&url)
        .header("Authorization", format!("Bearer {bearer_token}"))
        .multipart(form)
        .send()
        .await
        .map_err(|_| CsvError::Transport)?;
    let status = response.status().as_u16();
    // Log domain + status + counts only — NEVER cell values.
    log::info!(
        "canonical_csv.seal_box_and_upload status={} domain={} rows={}",
        status,
        domain.0,
        rows.len()
    );
    if !response.status().is_success() {
        return Err(CsvError::UploadRejected(status));
    }
    #[derive(Deserialize)]
    struct UploadResp {
        receipt_id: i64,
        bundle_id: Option<i64>,
        status: String,
    }
    let parsed: UploadResp = response
        .json()
        .await
        .map_err(|_| CsvError::UploadRejected(status))?;
    Ok(UploadReceipt {
        receipt_id: parsed.receipt_id,
        bundle_id: parsed.bundle_id,
        status: parsed.status,
        canonical_sha256: canonical_sha,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use sodiumoxide::crypto::box_::curve25519xsalsa20poly1305::gen_keypair;
    use sodiumoxide::crypto::sealedbox;
    use std::io::Write;

    #[test]
    fn canonical_headers_loads_at_least_20_domains() {
        let t = load_canonical_headers().unwrap();
        assert!(t.len() >= 20, "expected at least 20 canonical domains, got {}", t.len());
        assert!(t.contains_key("students"));
        assert!(t.contains_key("guardians"));
        assert!(t.contains_key("attendance"));
    }

    #[test]
    fn match_canonical_domain_students_happy_path() {
        let headers = vec![
            "external_id".to_string(),
            "first_name".to_string(),
            "last_name".to_string(),
            "grade_level".to_string(),
        ];
        let d = match_canonical_domain(&headers).unwrap();
        assert_eq!(d.0, "students");
    }

    #[test]
    fn match_canonical_domain_unknown_returns_none() {
        let headers = vec![
            "weather".to_string(),
            "temperature".to_string(),
            "humidity".to_string(),
        ];
        assert!(match_canonical_domain(&headers).is_none());
    }

    #[test]
    fn match_canonical_domain_below_min_hits_returns_none() {
        let headers = vec!["external_id".to_string(), "weird".to_string()];
        assert!(match_canonical_domain(&headers).is_none());
    }

    #[test]
    fn parse_csv_happy_path() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "external_id,first_name,last_name,grade_level").unwrap();
        writeln!(f, "s1,Alice,Adams,5").unwrap();
        writeln!(f, "s2,Bob,Brown,6").unwrap();
        f.flush().unwrap();
        let (headers, rows) = parse_csv(f.path()).unwrap();
        assert_eq!(headers, vec!["external_id", "first_name", "last_name", "grade_level"]);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].get("first_name").unwrap(), "Alice");
    }

    #[test]
    fn parse_csv_missing_file_errors() {
        let p = std::path::PathBuf::from("/nonexistent/missing.csv");
        assert!(matches!(parse_csv(&p), Err(CsvError::NotFound)));
    }

    #[test]
    fn seal_box_round_trip() {
        sodiumoxide::init().unwrap();
        let (pk, sk) = gen_keypair();
        let pk_b64 = B64.encode(pk.0);
        let plaintext = b"canonical bytes";
        let ciphertext = seal_box(plaintext, &pk_b64).unwrap();
        let opened = sealedbox::open(&ciphertext, &pk, &sk).unwrap();
        assert_eq!(opened, plaintext);
    }

    #[test]
    fn seal_box_rejects_bad_pubkey() {
        let r = seal_box(b"x", "not-base64!!!");
        assert!(matches!(r, Err(CsvError::BadPubkey)));
    }

    // --- detect_vendor integration via parse_and_preprocess ---

    #[test]
    fn parse_and_preprocess_detects_powerschool() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "Student Number,DCID,Enroll_Status,LastFirst").unwrap();
        writeln!(f, "10001,9999,A,\"Adams, Alice\"").unwrap();
        f.flush().unwrap();
        let (vendor, _, rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, Some("powerschool"));
        assert_eq!(rows[0].get("external_id").map(String::as_str), Some("10001"));
        assert_eq!(
            rows[0].get("enrollment_status").map(String::as_str),
            Some("active")
        );
    }

    #[test]
    fn parse_and_preprocess_detects_blackbaud() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(
            f,
            "Student.FirstName,Student.LastName,Student.Id,RelationshipType"
        )
        .unwrap();
        writeln!(f, "Bob,Brown,B-1,Mother").unwrap();
        f.flush().unwrap();
        let (vendor, _, rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, Some("blackbaud"));
        assert_eq!(rows[0].get("first_name").map(String::as_str), Some("Bob"));
    }

    #[test]
    fn parse_and_preprocess_detects_veracross() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "Person ID,Sex,Household ID,Role").unwrap();
        writeln!(f, "V-1,F,H-1,Student").unwrap();
        f.flush().unwrap();
        let (vendor, _, _rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, Some("veracross"));
    }

    #[test]
    fn parse_and_preprocess_detects_facts() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "FAMILYID,PERSONID,tuition_balance").unwrap();
        writeln!(f, "F-1,P-1,100").unwrap();
        f.flush().unwrap();
        let (vendor, _, _rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, Some("facts"));
    }

    #[test]
    fn parse_and_preprocess_detects_skyward() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "SKYWARD_ID,OTHER_ID,NAME_ID").unwrap();
        writeln!(f, "S-1,O-1,N-1").unwrap();
        f.flush().unwrap();
        let (vendor, _, _rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, Some("skyward"));
    }

    #[test]
    fn parse_and_preprocess_unknown_vendor_is_identity() {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        writeln!(f, "weather,temperature").unwrap();
        writeln!(f, "sunny,72").unwrap();
        f.flush().unwrap();
        let (vendor, _, rows) = parse_and_preprocess(f.path()).unwrap();
        assert_eq!(vendor, None);
        // Identity: original headers preserved verbatim.
        assert_eq!(rows[0].get("weather").map(String::as_str), Some("sunny"));
    }

    #[test]
    fn canonical_serialize_deterministic() {
        let mut a = HashMap::new();
        a.insert("external_id".to_string(), "s1".to_string());
        a.insert("first_name".to_string(), "Alice".to_string());
        let mut b = HashMap::new();
        b.insert("external_id".to_string(), "s2".to_string());
        b.insert("first_name".to_string(), "Bob".to_string());
        let rows1 = vec![
            CanonicalRow { fields: a.clone() },
            CanonicalRow { fields: b.clone() },
        ];
        let rows2 = vec![
            CanonicalRow { fields: b },
            CanonicalRow { fields: a },
        ];
        let s1 = canonical_serialize(&rows1);
        let s2 = canonical_serialize(&rows2);
        assert_eq!(s1, s2, "row order must not affect canonical bytes");
    }
}
