//! Vendor extractors — PURE DATA TRANSFORMS (v3.38.0 architectural boundary).
//!
//! Programmatic vendor login + DOM scraping + headless session replay
//! live in `companion-extension/` (the browser extension where the
//! operator's own authenticated tab is the security boundary). The
//! Tauri sibling does NOT and MUST NOT contain code that
//! programmatically logs into any third-party SIS.
//!
//! What these modules ARE: pre-processors that take already-parsed
//! CSV rows (`Vec<HashMap<String,String>>`) — the operator manually
//! exported them from their SIS via the SIS's own export UI — and
//! normalize vendor-specific quirks (date formats, header casing,
//! status codes, nested keys, JSON-in-cell, separators) BEFORE the
//! canonical-header mapper runs.
//!
//! What these modules ARE NOT: there is NO `reqwest::Client`, NO
//! cookie capture, NO session replay, NO HTTP call to any
//! third-party SIS endpoint. If you find yourself adding one, stop:
//! that work belongs in `companion-extension/` instead.

use std::collections::HashMap;

pub mod alma;
pub mod blackbaud;
pub mod facts;
pub mod powerschool;
pub mod skyward;
pub mod veracross;

/// Normalize a single header for vendor-detection scoring.
/// Lowercase, trim, replace whitespace/dots/hyphens with underscore,
/// strip surrounding quotes.
pub fn normalize_header(h: &str) -> String {
    let trimmed = h.trim().trim_matches('"').trim_matches('\'');
    let mut out = String::with_capacity(trimmed.len());
    let mut prev_underscore = false;
    for ch in trimmed.chars() {
        let c = ch.to_ascii_lowercase();
        let mapped = match c {
            ' ' | '\t' | '-' | '.' | '/' | '\\' => '_',
            _ => c,
        };
        if mapped == '_' {
            if prev_underscore {
                continue;
            }
            prev_underscore = true;
        } else {
            prev_underscore = false;
        }
        out.push(mapped);
    }
    out.trim_matches('_').to_string()
}

/// Vendor-signature header sets. Each tuple = (vendor_name, signature_lower_headers).
/// detect_vendor scores headers by overlap count; highest scorer wins.
/// Deterministic tie-break: alphabetic vendor name.
fn vendor_signatures() -> Vec<(&'static str, &'static [&'static str])> {
    vec![
        // PowerSchool: classic SIS export with "Student Number", "DCID",
        // "Enroll_Status", "LastFirst" headers.
        (
            "powerschool",
            &[
                "student_number",
                "dcid",
                "enroll_status",
                "lastfirst",
                "schoolid",
                "grade_level",
                "home_room",
                "entrydate",
                "exitdate",
            ],
        ),
        // Blackbaud (OnRecord / OnCampus): dot-nested headers like
        // "Student.FirstName".
        (
            "blackbaud",
            &[
                "student_firstname",
                "student_lastname",
                "student_id",
                "relationshiptype",
                "user_id",
                "host_id",
                "constituent_id",
                "user_modifieddate",
            ],
        ),
        // Veracross: role-partitioned exports, "Person ID", "Sex",
        // "Household ID".
        (
            "veracross",
            &[
                "person_id",
                "sex",
                "household_id",
                "studentemail",
                "facultyemail",
                "grad_year",
                "current_grade",
                "person_pk",
            ],
        ),
        // Alma: GraphQL-style export with JSON-in-cell.
        (
            "alma",
            &[
                "alma_id",
                "school_users_id",
                "user_type",
                "graphql_node",
                "extra_attributes",
                "custom_fields_json",
            ],
        ),
        // FACTS (ASPX-exported, tab-separated): "FAMILYID", "PERSONID".
        (
            "facts",
            &[
                "familyid",
                "personid",
                "tuition_balance",
                "facts_id",
                "school_year_id",
                "studentid",
                "renweb_id",
            ],
        ),
        // Skyward (legacy Mac line endings, ALL_CAPS headers):
        // "STUDENT_ID", "OTHER_ID".
        (
            "skyward",
            &[
                "skyward_id",
                "other_id",
                "name_id",
                "entity_id",
                "school_year",
                "homeroom_teacher",
                "gradyr",
            ],
        ),
    ]
}

/// Detect the source vendor from a list of CSV headers. Returns the
/// vendor name (`"powerschool"`, `"blackbaud"`, etc.) with the highest
/// signature-header overlap. Requires at least 1 overlap. Tie-broken
/// alphabetically for determinism.
pub fn detect_vendor(headers: &[String]) -> Option<&'static str> {
    let normalized: Vec<String> = headers.iter().map(|h| normalize_header(h)).collect();
    let sigs = vendor_signatures();
    let mut best: Option<(&'static str, usize)> = None;
    // Iterate in alphabetic order for deterministic tie-break.
    let mut ordered = sigs.clone();
    ordered.sort_by_key(|(name, _)| *name);
    for (vendor, sig_headers) in ordered.iter() {
        let hits = normalized
            .iter()
            .filter(|h| sig_headers.contains(&h.as_str()))
            .count();
        if hits == 0 {
            continue;
        }
        match best {
            None => best = Some((*vendor, hits)),
            Some((_, prev)) if hits > prev => best = Some((*vendor, hits)),
            _ => {}
        }
    }
    best.map(|(v, _)| v)
}

/// Dispatch a parsed-row vector to the appropriate vendor pre-processor.
/// Unknown vendor → identity (rows returned verbatim).
pub fn preprocess_for_vendor(
    vendor: Option<&str>,
    rows: Vec<HashMap<String, String>>,
) -> Vec<HashMap<String, String>> {
    match vendor {
        Some("powerschool") => powerschool::preprocess_rows(rows),
        Some("blackbaud") => blackbaud::preprocess_rows(rows),
        Some("veracross") => veracross::preprocess_rows(rows),
        Some("alma") => alma::preprocess_rows(rows),
        Some("facts") => facts::preprocess_rows(rows),
        Some("skyward") => skyward::preprocess_rows(rows),
        _ => rows,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_header_basic() {
        assert_eq!(normalize_header("Student Number"), "student_number");
        assert_eq!(normalize_header("  Enroll_Status  "), "enroll_status");
        assert_eq!(normalize_header("\"Student.FirstName\""), "student_firstname");
        assert_eq!(normalize_header("Person-ID"), "person_id");
    }

    #[test]
    fn detect_vendor_powerschool() {
        let h = vec![
            "Student Number".to_string(),
            "DCID".to_string(),
            "Enroll_Status".to_string(),
            "LastFirst".to_string(),
        ];
        assert_eq!(detect_vendor(&h), Some("powerschool"));
    }

    #[test]
    fn detect_vendor_blackbaud() {
        let h = vec![
            "Student.FirstName".to_string(),
            "Student.LastName".to_string(),
            "Student.Id".to_string(),
            "RelationshipType".to_string(),
        ];
        assert_eq!(detect_vendor(&h), Some("blackbaud"));
    }

    #[test]
    fn detect_vendor_veracross() {
        let h = vec![
            "Person ID".to_string(),
            "Sex".to_string(),
            "Household ID".to_string(),
            "StudentEmail".to_string(),
        ];
        assert_eq!(detect_vendor(&h), Some("veracross"));
    }

    #[test]
    fn detect_vendor_facts() {
        let h = vec![
            "FAMILYID".to_string(),
            "PERSONID".to_string(),
            "tuition_balance".to_string(),
        ];
        assert_eq!(detect_vendor(&h), Some("facts"));
    }

    #[test]
    fn detect_vendor_skyward() {
        let h = vec![
            "SKYWARD_ID".to_string(),
            "OTHER_ID".to_string(),
            "NAME_ID".to_string(),
        ];
        assert_eq!(detect_vendor(&h), Some("skyward"));
    }

    #[test]
    fn detect_vendor_unknown_returns_none() {
        let h = vec![
            "Temperature".to_string(),
            "Humidity".to_string(),
            "Pressure".to_string(),
        ];
        assert_eq!(detect_vendor(&h), None);
    }

    #[test]
    fn preprocess_for_vendor_unknown_is_identity() {
        let mut row = HashMap::new();
        row.insert("foo".to_string(), "bar".to_string());
        let out = preprocess_for_vendor(None, vec![row.clone()]);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].get("foo").map(String::as_str), Some("bar"));
    }
}
