//! Pre-processor for already-exported Blackbaud CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * Dot-nested keys flattened: `"Student.FirstName"` → `first_name`,
//!     `"Student.LastName"` → `last_name`, `"Student.Id"` →
//!     `external_id`.
//!   * Date format `YYYY-MM-DDTHH:MM:SS` truncated to `YYYY-MM-DD`.
//!   * Relationship rows: `RelationshipType` ∈ {Mother, Father,
//!     Guardian, Stepmother, Stepfather} → `guardian_relationship`
//!     (lowercased).
//!   * `User.Id` / `Constituent.Id` → `guardian_external_id` when
//!     `RelationshipType` is present on the row.

use std::collections::HashMap;

use super::normalize_header;

pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    // First pass: detect whether this is a guardian-relationship row.
    let is_guardian_row = row
        .keys()
        .any(|k| normalize_header(k) == "relationshiptype");

    let mut out: HashMap<String, String> = HashMap::new();
    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);
        let mapped = map_blackbaud_header(&norm, is_guardian_row);
        match mapped {
            BBField::ExternalId => {
                out.insert("external_id".to_string(), v);
            }
            BBField::GuardianExternalId => {
                out.insert("guardian_external_id".to_string(), v);
            }
            BBField::StudentExternalId => {
                out.insert("student_external_id".to_string(), v);
            }
            BBField::FirstName => {
                out.insert("first_name".to_string(), v);
            }
            BBField::LastName => {
                out.insert("last_name".to_string(), v);
            }
            BBField::MiddleName => {
                out.insert("middle_name".to_string(), v);
            }
            BBField::Email => {
                out.insert("email".to_string(), v);
            }
            BBField::Phone => {
                out.insert("phone".to_string(), v);
            }
            BBField::DateOfBirth => {
                out.insert("date_of_birth".to_string(), truncate_iso_datetime(&v));
            }
            BBField::EnrollmentDate => {
                out.insert("enrollment_date".to_string(), truncate_iso_datetime(&v));
            }
            BBField::ExitDate => {
                out.insert("exit_date".to_string(), truncate_iso_datetime(&v));
            }
            BBField::GuardianRelationship => {
                out.insert(
                    "guardian_relationship".to_string(),
                    normalize_relationship(&v),
                );
            }
            BBField::GradeLevel => {
                out.insert("grade_level".to_string(), v);
            }
            BBField::Gender => {
                out.insert("gender".to_string(), v.trim().to_string());
            }
            BBField::Passthrough => {
                out.insert(norm, v);
            }
        }
    }
    out
}

enum BBField {
    ExternalId,
    GuardianExternalId,
    StudentExternalId,
    FirstName,
    LastName,
    MiddleName,
    Email,
    Phone,
    DateOfBirth,
    EnrollmentDate,
    ExitDate,
    GuardianRelationship,
    GradeLevel,
    Gender,
    Passthrough,
}

fn map_blackbaud_header(norm: &str, is_guardian_row: bool) -> BBField {
    match norm {
        "student_firstname" | "first_name" | "firstname" => BBField::FirstName,
        "student_lastname" | "last_name" | "lastname" => BBField::LastName,
        "student_middlename" | "middle_name" | "middlename" => BBField::MiddleName,
        "student_id" => BBField::ExternalId,
        "user_id" | "constituent_id" | "host_id" => {
            if is_guardian_row {
                BBField::GuardianExternalId
            } else {
                BBField::ExternalId
            }
        }
        "student_external_id" => BBField::StudentExternalId,
        "student_email" | "user_email" | "email" => BBField::Email,
        "student_phone" | "user_phone" | "phone" => BBField::Phone,
        "student_dateofbirth" | "dateofbirth" | "date_of_birth" => BBField::DateOfBirth,
        "enrollmentdate" | "enrollment_date" => BBField::EnrollmentDate,
        "exitdate" | "exit_date" => BBField::ExitDate,
        "relationshiptype" => BBField::GuardianRelationship,
        "student_gradelevel" | "grade_level" | "gradelevel" => BBField::GradeLevel,
        "student_gender" | "gender" => BBField::Gender,
        _ => BBField::Passthrough,
    }
}

/// Truncate an ISO datetime `YYYY-MM-DDTHH:MM:SS[.fff][Z]` to
/// `YYYY-MM-DD`. If the input is already date-only, pass through. If
/// the input is not a recognized ISO format, pass through verbatim.
fn truncate_iso_datetime(s: &str) -> String {
    let t = s.trim();
    if t.is_empty() {
        return String::new();
    }
    // Accept up to the first 'T' or first space.
    let candidate: &str = match t.find('T').or_else(|| t.find(' ')) {
        Some(i) => &t[..i],
        None => t,
    };
    // Validate looks like `YYYY-MM-DD`.
    let parts: Vec<&str> = candidate.split('-').collect();
    if parts.len() != 3 || parts[0].len() != 4 {
        return t.to_string();
    }
    if !parts.iter().all(|p| p.chars().all(|c| c.is_ascii_digit())) {
        return t.to_string();
    }
    candidate.to_string()
}

fn normalize_relationship(s: &str) -> String {
    let t = s.trim();
    let lower = t.to_ascii_lowercase();
    match lower.as_str() {
        "mother" | "father" | "guardian" | "stepmother" | "stepfather"
        | "grandmother" | "grandfather" | "aunt" | "uncle" => lower,
        _ => t.to_string(),
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
    fn dot_nested_firstname_flattens() {
        let r = row(&[("Student.FirstName", "Bob")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("first_name").map(String::as_str), Some("Bob"));
    }

    #[test]
    fn iso_datetime_truncates_to_date() {
        let r = row(&[("Student.DateOfBirth", "2010-03-15T08:00:00Z")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("2010-03-15")
        );
    }

    #[test]
    fn relationship_row_user_id_becomes_guardian_id() {
        let r = row(&[
            ("RelationshipType", "Mother"),
            ("User.Id", "G-99"),
        ]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("guardian_external_id").map(String::as_str),
            Some("G-99")
        );
        assert_eq!(
            out[0].get("guardian_relationship").map(String::as_str),
            Some("mother")
        );
    }

    #[test]
    fn non_relationship_user_id_stays_external_id() {
        let r = row(&[("User.Id", "U-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("U-1"));
        assert!(out[0].get("guardian_external_id").is_none());
    }

    #[test]
    fn unknown_relationship_passes_through_trimmed() {
        let r = row(&[("RelationshipType", "FosterParent")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("guardian_relationship").map(String::as_str),
            Some("FosterParent")
        );
    }

    #[test]
    fn non_iso_date_preserved() {
        let r = row(&[("Student.DateOfBirth", "invalid")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("date_of_birth").map(String::as_str),
            Some("invalid")
        );
    }

    #[test]
    fn deterministic_output() {
        let r = row(&[
            ("Student.FirstName", "A"),
            ("Student.LastName", "B"),
            ("Student.Id", "1"),
        ]);
        let a = preprocess_rows(vec![r.clone()]);
        let b = preprocess_rows(vec![r]);
        assert_eq!(a, b);
    }
}
