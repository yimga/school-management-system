//! Pre-processor for already-exported Veracross CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * Role-partitioned columns: pick by role. If `Person Type` /
//!     `Role` ∈ {Student, Faculty, Staff, Parent}, prefer the
//!     matching role-prefixed column (e.g. `StudentEmail` vs
//!     `FacultyEmail`). When `Role` is missing, both columns are
//!     preserved under their normalized names.
//!   * Date format `M/D/YYYY` (single-digit possible) → ISO-8601.
//!   * Gender via `"Sex"` column → `gender`.
//!   * `Person ID` → `external_id` (or `staff_external_id` for
//!     Faculty/Staff rows).

use std::collections::HashMap;

use super::normalize_header;

pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Role {
    Student,
    Faculty,
    Staff,
    Parent,
    Unknown,
}

fn detect_role(row: &HashMap<String, String>) -> Role {
    for (k, v) in row.iter() {
        let nk = normalize_header(k);
        if matches!(nk.as_str(), "role" | "person_type" | "constituent_type") {
            let lv = v.trim().to_ascii_lowercase();
            return match lv.as_str() {
                "student" => Role::Student,
                "faculty" => Role::Faculty,
                "staff" => Role::Staff,
                "parent" | "guardian" => Role::Parent,
                _ => Role::Unknown,
            };
        }
    }
    Role::Unknown
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    let role = detect_role(&row);
    let mut out: HashMap<String, String> = HashMap::new();

    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);

        // Role-partitioned columns: only emit the canonical key if
        // this column's prefix matches the row's role.
        if let Some(rest) = role_prefix_strip(&norm) {
            let (prefix, suffix) = rest;
            let matches = match (prefix, role) {
                ("student", Role::Student) => true,
                ("faculty", Role::Faculty) => true,
                ("staff", Role::Staff) => true,
                ("parent", Role::Parent) => true,
                // Unknown role: preserve as suffixed-key but keep
                // both flavors under their normalized names.
                _ => false,
            };
            if matches {
                let canonical = match suffix {
                    "email" => "email",
                    "phone" => "phone",
                    "firstname" => "first_name",
                    "lastname" => "last_name",
                    other => other,
                };
                out.insert(canonical.to_string(), v);
            } else {
                // Preserve under normalized key so server-side mapper
                // sees it as a custom field.
                out.insert(norm, v);
            }
            continue;
        }

        match norm.as_str() {
            "person_id" | "person_pk" => {
                let key = match role {
                    Role::Faculty | Role::Staff => "staff_external_id",
                    Role::Parent => "guardian_external_id",
                    _ => "external_id",
                };
                out.insert(key.to_string(), v);
            }
            "first_name" | "firstname" => {
                out.insert("first_name".to_string(), v);
            }
            "last_name" | "lastname" => {
                out.insert("last_name".to_string(), v);
            }
            "sex" | "gender" => {
                out.insert("gender".to_string(), v.trim().to_string());
            }
            "current_grade" | "grade_level" | "grade" => {
                out.insert("grade_level".to_string(), v);
            }
            "grad_year" | "graduation_year" => {
                out.insert("graduation_year".to_string(), v);
            }
            "birth_date" | "birthdate" | "date_of_birth" | "dob" => {
                out.insert("date_of_birth".to_string(), normalize_slash_date(&v));
            }
            "enrollment_date" => {
                out.insert("enrollment_date".to_string(), normalize_slash_date(&v));
            }
            "household_id" => {
                out.insert("household_id".to_string(), v);
            }
            _ => {
                out.insert(norm, v);
            }
        }
    }
    out
}

fn role_prefix_strip(norm: &str) -> Option<(&'static str, &str)> {
    for p in &["student", "faculty", "staff", "parent"] {
        if let Some(rest) = norm.strip_prefix(*p) {
            let r = rest.trim_start_matches('_');
            if r.is_empty() {
                continue;
            }
            return Some((p, r));
        }
    }
    None
}

/// Normalize `M/D/YYYY` (single-digit components possible) to
/// `YYYY-MM-DD`. Falls through on parse failure.
fn normalize_slash_date(s: &str) -> String {
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
    if mi == 0 || mi > 12 || di == 0 || di > 31 {
        return t.to_string();
    }
    // Veracross 4-digit years assumed; if 2-digit, leave untouched.
    if y.len() != 4 {
        return t.to_string();
    }
    format!("{:04}-{:02}-{:02}", yi, mi, di)
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
    fn role_student_picks_student_email() {
        let r = row(&[
            ("Role", "Student"),
            ("StudentEmail", "s@s.com"),
            ("FacultyEmail", "f@f.com"),
        ]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("email").map(String::as_str), Some("s@s.com"));
    }

    #[test]
    fn role_faculty_picks_faculty_email() {
        let r = row(&[
            ("Role", "Faculty"),
            ("StudentEmail", "s@s.com"),
            ("FacultyEmail", "f@f.com"),
        ]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("email").map(String::as_str), Some("f@f.com"));
    }

    #[test]
    fn slash_date_to_iso_single_digit() {
        let r = row(&[("DOB", "3/5/2010")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("2010-03-05")
        );
    }

    #[test]
    fn person_id_faculty_becomes_staff_external_id() {
        let r = row(&[("Role", "Faculty"), ("Person ID", "F-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("staff_external_id").map(String::as_str),
            Some("F-1")
        );
    }

    #[test]
    fn sex_column_maps_to_gender() {
        let r = row(&[("Role", "Student"), ("Sex", "F")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("gender").map(String::as_str), Some("F"));
    }

    #[test]
    fn unknown_role_preserves_both_emails() {
        let r = row(&[("StudentEmail", "a@a.com"), ("FacultyEmail", "b@b.com")]);
        let out = preprocess_rows(vec![r]);
        assert!(out[0].contains_key("studentemail") || out[0].contains_key("student_email"));
        assert!(out[0].contains_key("facultyemail") || out[0].contains_key("faculty_email"));
    }

    #[test]
    fn deterministic_output() {
        let r = row(&[("Role", "Student"), ("Person ID", "1")]);
        let a = preprocess_rows(vec![r.clone()]);
        let b = preprocess_rows(vec![r]);
        assert_eq!(a, b);
    }
}
