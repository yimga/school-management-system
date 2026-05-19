//! Pre-processor for already-exported PowerSchool CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * Header normalization: `"Student Number"` → `student_number`,
//!     `"Enroll_Status"` → `enrollment_status`, `"LastFirst"` →
//!     decomposed into `last_name` + `first_name`, `"DOB"` →
//!     `date_of_birth`.
//!   * Date format `MM/DD/YYYY` → ISO-8601 (`YYYY-MM-DD`).
//!   * Gender codes `M`/`F`/`O`/`U` pass through.
//!   * Enrollment status: `A` → `active`, `I` → `inactive`,
//!     `T` → `transferred`, `G` → `graduated`. Anything else is
//!     preserved verbatim.

use std::collections::HashMap;

use super::normalize_header;

/// Pre-process a vector of already-parsed PowerSchool CSV rows.
/// Pure function, no IO.
pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    let mut out: HashMap<String, String> = HashMap::new();
    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);
        match norm.as_str() {
            "student_number" => {
                out.insert("external_id".to_string(), v);
            }
            "lastfirst" => {
                // PowerSchool's `LastFirst` is "Lastname, Firstname".
                let parts: Vec<&str> = v.splitn(2, ',').collect();
                if parts.len() == 2 {
                    out.insert("last_name".to_string(), parts[0].trim().to_string());
                    out.insert("first_name".to_string(), parts[1].trim().to_string());
                } else {
                    // Single token — preserve as last_name.
                    out.insert("last_name".to_string(), v.trim().to_string());
                }
            }
            "first_name" | "firstname" => {
                out.insert("first_name".to_string(), v);
            }
            "last_name" | "lastname" => {
                out.insert("last_name".to_string(), v);
            }
            "middle_name" | "middlename" => {
                out.insert("middle_name".to_string(), v);
            }
            "dob" | "date_of_birth" => {
                out.insert("date_of_birth".to_string(), normalize_us_date(&v));
            }
            "entrydate" => {
                out.insert("enrollment_date".to_string(), normalize_us_date(&v));
            }
            "exitdate" => {
                out.insert("exit_date".to_string(), normalize_us_date(&v));
            }
            "gender" | "sex" => {
                out.insert("gender".to_string(), normalize_gender(&v));
            }
            "enroll_status" | "enrollment_status" => {
                out.insert("enrollment_status".to_string(), normalize_status(&v));
            }
            "grade_level" => {
                out.insert("grade_level".to_string(), v);
            }
            "home_phone" | "phone" => {
                out.insert("phone".to_string(), v);
            }
            "student_email" | "email" => {
                out.insert("email".to_string(), v);
            }
            _ => {
                // Unknown header: keep normalized name so server-side
                // mapper can route to custom_fields.
                out.insert(norm, v);
            }
        }
    }
    out
}

/// Convert `MM/DD/YYYY` (or `M/D/YYYY`) to `YYYY-MM-DD`. Returns the
/// original string when parsing fails (preserves data; the server
/// mapper can flag it).
fn normalize_us_date(s: &str) -> String {
    let t = s.trim();
    if t.is_empty() {
        return String::new();
    }
    let parts: Vec<&str> = t.split('/').collect();
    if parts.len() != 3 {
        return t.to_string();
    }
    let (m, d, y) = (parts[0], parts[1], parts[2]);
    if !m.chars().all(|c| c.is_ascii_digit())
        || !d.chars().all(|c| c.is_ascii_digit())
        || !y.chars().all(|c| c.is_ascii_digit())
    {
        return t.to_string();
    }
    let (mi, di, yi) = match (m.parse::<u32>(), d.parse::<u32>(), y.parse::<u32>()) {
        (Ok(a), Ok(b), Ok(c)) => (a, b, c),
        _ => return t.to_string(),
    };
    if mi == 0 || mi > 12 || di == 0 || di > 31 || y.len() != 4 {
        return t.to_string();
    }
    format!("{:04}-{:02}-{:02}", yi, mi, di)
}

fn normalize_gender(s: &str) -> String {
    let t = s.trim().to_ascii_uppercase();
    match t.as_str() {
        "M" | "F" | "O" | "U" => t,
        _ => s.trim().to_string(),
    }
}

fn normalize_status(s: &str) -> String {
    let t = s.trim().to_ascii_uppercase();
    match t.as_str() {
        "A" => "active".to_string(),
        "I" => "inactive".to_string(),
        "T" => "transferred".to_string(),
        "G" => "graduated".to_string(),
        _ => s.trim().to_string(),
    }
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
    fn student_number_maps_to_external_id() {
        let r = row(&[("Student Number", "10001")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("10001"));
    }

    #[test]
    fn lastfirst_splits_into_first_last() {
        let r = row(&[("LastFirst", "Adams, Alice")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("last_name").map(String::as_str), Some("Adams"));
        assert_eq!(out[0].get("first_name").map(String::as_str), Some("Alice"));
    }

    #[test]
    fn us_date_to_iso() {
        let r = row(&[("DOB", "03/15/2010")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("date_of_birth").map(String::as_str), Some("2010-03-15"));
    }

    #[test]
    fn enrollment_status_letter_to_word() {
        let r = row(&[("Enroll_Status", "A")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("enrollment_status").map(String::as_str),
            Some("active")
        );
        let r2 = row(&[("Enroll_Status", "I")]);
        let out2 = preprocess_rows(vec![r2]);
        assert_eq!(
            out2[0].get("enrollment_status").map(String::as_str),
            Some("inactive")
        );
    }

    #[test]
    fn gender_passthrough() {
        let r = row(&[("Gender", "F")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("gender").map(String::as_str), Some("F"));
    }

    #[test]
    fn invalid_date_passes_through() {
        let r = row(&[("DOB", "not-a-date")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("not-a-date")
        );
    }

    #[test]
    fn deterministic_output_for_same_input() {
        let r1 = row(&[("Student Number", "1"), ("DOB", "01/02/2010")]);
        let r2 = row(&[("Student Number", "2"), ("DOB", "03/04/2011")]);
        let a = preprocess_rows(vec![r1.clone(), r2.clone()]);
        let b = preprocess_rows(vec![r1, r2]);
        assert_eq!(a, b);
    }

    #[test]
    fn empty_date_stays_empty() {
        let r = row(&[("DOB", "")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("date_of_birth").map(String::as_str), Some(""));
    }
}
