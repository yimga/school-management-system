//! Pre-processor for already-exported Skyward CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * Skyward CSVs use `\r` line endings (legacy Mac) — by the time
//!     rows reach this pre-processor the upstream CSV parser has
//!     already split them, but cell values may carry a trailing
//!     `\r` that we strip here defensively.
//!   * Column names ALL_CAPS_WITH_UNDERSCORES — normalized to
//!     lowercase by `super::normalize_header`.
//!   * Date format `YYYYMMDD` (8 digits, no separator) → ISO-8601.
//!     Already-ISO dates pass through.
//!   * `SKYWARD_ID` or `OTHER_ID` → `external_id`; `NAME_ID` →
//!     `name_id` (passthrough — Skyward uses it for guardian links).
//!   * Write-path fields carry an EXPLICIT
//!     `# honest-stub: write-path counsel-blocked` marker; READ
//!     path implemented (passthrough under `read_only_` prefix).

use std::collections::HashMap;

use super::normalize_header;

pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    let mut out: HashMap<String, String> = HashMap::new();
    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);
        let value: String = v.trim_end_matches('\r').to_string();

        match norm.as_str() {
            "skyward_id" | "other_id" => {
                out.insert("external_id".to_string(), value);
            }
            "name_id" => {
                out.insert("name_id".to_string(), value);
            }
            "entity_id" => {
                out.insert("entity_id".to_string(), value);
            }
            "first_name" | "firstname" | "fname" => {
                out.insert("first_name".to_string(), value);
            }
            "last_name" | "lastname" | "lname" => {
                out.insert("last_name".to_string(), value);
            }
            "middle_name" | "middlename" | "mname" => {
                out.insert("middle_name".to_string(), value);
            }
            "email_address" | "email" | "email_addr" => {
                out.insert("email".to_string(), value);
            }
            "phone_number" | "phone" => {
                out.insert("phone".to_string(), value);
            }
            "birthdate" | "birth_date" | "dob" | "date_of_birth" => {
                out.insert("date_of_birth".to_string(), normalize_compact_date(&value));
            }
            "entry_date" | "enrollment_date" => {
                out.insert("enrollment_date".to_string(), normalize_compact_date(&value));
            }
            "exit_date" | "withdraw_date" => {
                out.insert("exit_date".to_string(), normalize_compact_date(&value));
            }
            "grade_level" | "grade" | "grad_level" | "gradyr" => {
                out.insert("grade_level".to_string(), value);
            }
            "gender" | "sex" => {
                out.insert("gender".to_string(), value.trim().to_string());
            }
            "homeroom_teacher" => {
                out.insert("homeroom_teacher".to_string(), value);
            }
            // Write-path counsel-blocked — read-only passthrough.
            // honest-stub: write-path counsel-blocked
            "status" | "enroll_status" | "enrollment_status" => {
                out.insert("read_only_status".to_string(), value);
            }
            // honest-stub: write-path counsel-blocked
            "balance" | "fee_balance" => {
                out.insert("read_only_balance".to_string(), value);
            }
            _ => {
                out.insert(norm, value);
            }
        }
    }
    out
}

/// Normalize Skyward's compact `YYYYMMDD` date to ISO-8601. Already-
/// ISO `YYYY-MM-DD` strings pass through. Fall through on anything
/// else.
fn normalize_compact_date(s: &str) -> String {
    let t = s.trim();
    if t.is_empty() {
        return String::new();
    }
    // Already-ISO short-circuit.
    if t.len() == 10 && &t[4..5] == "-" && &t[7..8] == "-" {
        return t.to_string();
    }
    if t.len() != 8 || !t.chars().all(|c| c.is_ascii_digit()) {
        return t.to_string();
    }
    let (y_s, rest) = t.split_at(4);
    let (m_s, d_s) = rest.split_at(2);
    let (y, m, d) = match (
        y_s.parse::<u32>(),
        m_s.parse::<u32>(),
        d_s.parse::<u32>(),
    ) {
        (Ok(a), Ok(b), Ok(c)) => (a, b, c),
        _ => return t.to_string(),
    };
    if m == 0 || m > 12 || d == 0 || d > 31 {
        return t.to_string();
    }
    format!("{:04}-{:02}-{:02}", y, m, d)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
            .collect()
    }

    #[test]
    fn skyward_id_maps_to_external_id() {
        let r = row(&[("SKYWARD_ID", "SK-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("SK-1"));
    }

    #[test]
    fn other_id_maps_to_external_id() {
        let r = row(&[("OTHER_ID", "O-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("O-1"));
    }

    #[test]
    fn compact_date_to_iso() {
        let r = row(&[("BIRTHDATE", "20100315")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("2010-03-15")
        );
    }

    #[test]
    fn iso_date_passes_through() {
        let r = row(&[("BIRTHDATE", "2010-03-15")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("2010-03-15")
        );
    }

    #[test]
    fn trailing_cr_is_stripped() {
        let r = row(&[("FIRST_NAME", "Alice\r")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("first_name").map(String::as_str), Some("Alice"));
    }

    #[test]
    fn write_path_status_goes_to_read_only_prefix() {
        let r = row(&[("STATUS", "ACTIVE")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("read_only_status").map(String::as_str),
            Some("ACTIVE")
        );
        assert!(out[0].get("status").is_none());
    }

    #[test]
    fn deterministic_output() {
        let r = row(&[("SKYWARD_ID", "1"), ("BIRTHDATE", "20100101")]);
        let a = preprocess_rows(vec![r.clone()]);
        let b = preprocess_rows(vec![r]);
        assert_eq!(a, b);
    }
}
