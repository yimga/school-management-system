//! Pre-processor for already-exported FACTS CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * FACTS ASPX-exported CSV uses `\t` separator and `\r\n` line
//!     endings. NOTE: separator + line-ending handling is the
//!     responsibility of the upstream CSV parser. By the time rows
//!     reach `preprocess_rows`, each row is already a HashMap. This
//!     module trims `\r` carriage-return remnants from cell values.
//!   * Date format `MM/DD/YY` (2-digit year) → ISO-8601, windowed to
//!     1950-2049 (years 0-49 → 2000s, 50-99 → 1900s).
//!   * `FAMILYID` → `household_id`, `PERSONID` → `external_id`,
//!     `STUDENTID` → `student_external_id`.
//!   * Write-path fields (status changes, balance updates) carry an
//!     EXPLICIT `# honest-stub: write-path counsel-blocked` marker;
//!     the READ path is implemented (we pass them through under a
//!     `read_only_` prefix so the server-side mapper knows not to
//!     attempt write-back).

use std::collections::HashMap;

use super::normalize_header;

pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    let mut out: HashMap<String, String> = HashMap::new();
    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);
        // Strip stray CR from any cell value (defensive — upstream
        // parser usually handles \r\n, but tab-separated ASPX exports
        // occasionally leak a trailing \r inside the last column).
        let value: String = v.trim_end_matches('\r').to_string();

        match norm.as_str() {
            "familyid" | "family_id" => {
                out.insert("household_id".to_string(), value);
            }
            "personid" | "person_id" => {
                out.insert("external_id".to_string(), value);
            }
            "studentid" | "student_id" => {
                out.insert("student_external_id".to_string(), value);
            }
            "firstname" | "first_name" => {
                out.insert("first_name".to_string(), value);
            }
            "lastname" | "last_name" => {
                out.insert("last_name".to_string(), value);
            }
            "middlename" | "middle_name" => {
                out.insert("middle_name".to_string(), value);
            }
            "email" | "emailaddress" => {
                out.insert("email".to_string(), value);
            }
            "phone" | "phonenumber" => {
                out.insert("phone".to_string(), value);
            }
            "dob" | "birthdate" | "date_of_birth" => {
                out.insert("date_of_birth".to_string(), normalize_short_year_date(&value));
            }
            "enrollmentdate" | "enrollment_date" => {
                out.insert(
                    "enrollment_date".to_string(),
                    normalize_short_year_date(&value),
                );
            }
            // Write-path fields — read-only passthrough.
            // honest-stub: write-path counsel-blocked
            "tuition_balance" | "balance" => {
                out.insert("read_only_balance".to_string(), value);
            }
            // honest-stub: write-path counsel-blocked
            "enrollmentstatus" | "enrollment_status" | "status" => {
                out.insert("read_only_status".to_string(), value);
            }
            "grade" | "grade_level" | "gradelevel" => {
                out.insert("grade_level".to_string(), value);
            }
            _ => {
                out.insert(norm, value);
            }
        }
    }
    out
}

/// Convert `MM/DD/YY` (2-digit year) to `YYYY-MM-DD`. Window:
/// year 00-49 → 2000-2049, 50-99 → 1950-1999. Falls through on parse
/// failure; also accepts 4-digit year by delegating to the 4-digit
/// normalizer.
fn normalize_short_year_date(s: &str) -> String {
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
    let mi = m.parse::<u32>().ok();
    let di = d.parse::<u32>().ok();
    let yi = y.parse::<u32>().ok();
    let (mi, di, yi) = match (mi, di, yi) {
        (Some(a), Some(b), Some(c)) => (a, b, c),
        _ => return t.to_string(),
    };
    if mi == 0 || mi > 12 || di == 0 || di > 31 {
        return t.to_string();
    }
    let full_year: u32 = match y.len() {
        2 => {
            if yi <= 49 {
                2000 + yi
            } else {
                1900 + yi
            }
        }
        4 => yi,
        _ => return t.to_string(),
    };
    format!("{:04}-{:02}-{:02}", full_year, mi, di)
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
    fn familyid_maps_to_household_id() {
        let r = row(&[("FAMILYID", "F-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("household_id").map(String::as_str), Some("F-1"));
    }

    #[test]
    fn personid_maps_to_external_id() {
        let r = row(&[("PERSONID", "P-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("P-1"));
    }

    #[test]
    fn short_year_date_windowed_to_2000s() {
        let r = row(&[("DOB", "03/15/10")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("2010-03-15")
        );
    }

    #[test]
    fn short_year_date_windowed_to_1900s() {
        let r = row(&[("DOB", "06/20/75")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("1975-06-20")
        );
    }

    #[test]
    fn write_path_balance_goes_to_read_only_prefix() {
        let r = row(&[("tuition_balance", "1234.56")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("read_only_balance").map(String::as_str),
            Some("1234.56")
        );
        assert!(out[0].get("balance").is_none());
    }

    #[test]
    fn trailing_cr_is_stripped() {
        let r = row(&[("FAMILYID", "F-99\r")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("household_id").map(String::as_str), Some("F-99"));
    }

    #[test]
    fn deterministic_output() {
        let r = row(&[("PERSONID", "1"), ("DOB", "01/02/05")]);
        let a = preprocess_rows(vec![r.clone()]);
        let b = preprocess_rows(vec![r]);
        assert_eq!(a, b);
    }
}
