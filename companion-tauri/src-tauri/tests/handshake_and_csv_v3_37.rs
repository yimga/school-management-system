//! Integration tests for the v3.37.0 Tauri sibling handshake + CSV
//! ingest modules. 8 #[test] cases as required by Agent 4 scope.
//!
//! These tests do NOT require a live RMC server. The crypto +
//! canonical-domain + CSV paths are exercised purely with local
//! sodiumoxide + the bundled canonical_headers.json.

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use runmycampus_companion_tauri_lib::canonical_csv::{
    canonical_serialize, load_canonical_headers, match_canonical_domain, parse_csv, seal_box,
    CanonicalRow, CsvError,
};
use runmycampus_companion_tauri_lib::rmc_handshake::{Credentials, HandshakeError, SessionToken};
use sodiumoxide::crypto::box_::curve25519xsalsa20poly1305::gen_keypair;
use sodiumoxide::crypto::sealedbox;
use std::collections::HashMap;
use std::io::Write;

#[test]
fn t1_csv_parse_happy_path() {
    let mut f = tempfile::NamedTempFile::new().unwrap();
    writeln!(f, "external_id,first_name,last_name,grade_level").unwrap();
    writeln!(f, "s1,Alice,Adams,5").unwrap();
    writeln!(f, "s2,Bob,Brown,6").unwrap();
    f.flush().unwrap();
    let (headers, rows) = parse_csv(f.path()).unwrap();
    assert_eq!(headers.len(), 4);
    assert_eq!(rows.len(), 2);
}

#[test]
fn t2_csv_with_vendor_headers_maps_to_students_domain() {
    let mut f = tempfile::NamedTempFile::new().unwrap();
    writeln!(
        f,
        "external_id,first_name,last_name,date_of_birth,grade_level,enrollment_status"
    )
    .unwrap();
    writeln!(f, "ps_123,Alice,Adams,2010-01-01,5,active").unwrap();
    f.flush().unwrap();
    let (headers, _) = parse_csv(f.path()).unwrap();
    let d = match_canonical_domain(&headers).unwrap();
    assert_eq!(d.0, "students");
}

#[test]
fn t3_csv_unknown_domain_returns_none() {
    let headers = vec![
        "totally".to_string(),
        "unrelated".to_string(),
        "headers".to_string(),
    ];
    assert!(match_canonical_domain(&headers).is_none());
}

#[test]
fn t4_sealed_box_round_trip_with_libsodium() {
    sodiumoxide::init().unwrap();
    let (pk, sk) = gen_keypair();
    let pk_b64 = B64.encode(pk.0);
    let plaintext = b"hello canonical bytes";
    let ciphertext = seal_box(plaintext, &pk_b64).unwrap();
    let opened = sealedbox::open(&ciphertext, &pk, &sk).unwrap();
    assert_eq!(opened, plaintext);
}

#[test]
fn t5_token_zeroized_on_drop_trait_present() {
    fn assert_zod<T: zeroize::ZeroizeOnDrop>(_: &T) {}
    let t = SessionToken::new("abc.xyz".into());
    assert_zod(&t);
    let c = Credentials {
        email: "a@b".into(),
        password: "p".into(),
    };
    assert_zod(&c);
}

#[test]
fn t6_login_error_mapping_401_unauthorized() {
    // We can't reach a live server here; instead assert the public
    // typed-error variants exist and serialize as expected.
    let e = HandshakeError::Unauthorized;
    assert_eq!(format!("{e}"), "authentication failed (401)");
}

#[test]
fn t7_maa_fetch_error_mapping() {
    let e = HandshakeError::MaaFetchFailed;
    assert_eq!(format!("{e}"), "MAA fetch failed");
    let e2: HandshakeError = HandshakeError::BadServerUrl;
    assert_eq!(format!("{e2}"), "invalid server URL");
}

#[test]
fn t8_canonical_headers_json_loads_at_least_20_domains() {
    let t = load_canonical_headers().unwrap();
    assert!(t.len() >= 20);
    // Spot-check a few known canonical domains:
    for d in [
        "students",
        "staff",
        "guardians",
        "attendance",
        "grades",
        "transport",
        "hostel",
        "cafeteria",
        "alumni",
        "compliance",
    ] {
        assert!(t.contains_key(d), "missing canonical domain: {d}");
    }
}

// Bonus regression: canonical_serialize is order-independent across
// row order — guarantees idempotency-key uploads land the same SHA.
#[test]
fn t9_canonical_serialize_is_row_order_independent() {
    let mut a = HashMap::new();
    a.insert("external_id".to_string(), "s1".to_string());
    let mut b = HashMap::new();
    b.insert("external_id".to_string(), "s2".to_string());
    let r1 = vec![CanonicalRow { fields: a.clone() }, CanonicalRow { fields: b.clone() }];
    let r2 = vec![CanonicalRow { fields: b }, CanonicalRow { fields: a }];
    assert_eq!(canonical_serialize(&r1), canonical_serialize(&r2));
}

// Bonus: missing file path returns NotFound (not panic).
#[test]
fn t10_parse_csv_missing_file_returns_notfound() {
    let p = std::path::PathBuf::from("Z:/no/such/file/at/all.csv");
    assert!(matches!(parse_csv(&p), Err(CsvError::NotFound)));
}
