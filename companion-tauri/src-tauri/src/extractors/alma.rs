//! Pre-processor for already-exported Alma CSV. Does NOT touch network or SIS auth — pure data transform.
//!
//! Rules (v3.38.0):
//!   * GraphQL-export-formatted JSON-in-CSV cells: e.g.
//!     `"{""grade"":""9""}"` are parsed safely and flattened one
//!     level into top-level keys. JSON parse failure → preserve the
//!     raw cell verbatim (no panic).
//!   * Nullable handling: literal `"null"` and empty string → empty
//!     string (server-mapper treats both the same).
//!   * `alma_id` or `school_users_id` → `external_id`.
//!   * `user_type` → `role`.

use std::collections::HashMap;

use super::normalize_header;

pub fn preprocess_rows(rows: Vec<HashMap<String, String>>) -> Vec<HashMap<String, String>> {
    rows.into_iter().map(preprocess_row).collect()
}

fn preprocess_row(row: HashMap<String, String>) -> HashMap<String, String> {
    let mut out: HashMap<String, String> = HashMap::new();
    for (raw_k, v) in row.into_iter() {
        let norm = normalize_header(&raw_k);
        let value = denull(&v);

        match norm.as_str() {
            "alma_id" | "school_users_id" => {
                out.insert("external_id".to_string(), value.to_string());
            }
            "user_type" => {
                out.insert("role".to_string(), value.to_string());
            }
            "first_name" | "firstname" => {
                out.insert("first_name".to_string(), value.to_string());
            }
            "last_name" | "lastname" => {
                out.insert("last_name".to_string(), value.to_string());
            }
            "email" => {
                out.insert("email".to_string(), value.to_string());
            }
            "phone" => {
                out.insert("phone".to_string(), value.to_string());
            }
            "extra_attributes" | "custom_fields_json" | "graphql_node" => {
                // JSON-in-CSV: parse and flatten one level. On failure,
                // preserve the raw cell under the normalized key.
                match flatten_json_one_level(value) {
                    Some(pairs) => {
                        for (k, v) in pairs {
                            // Don't clobber existing canonical keys.
                            out.entry(k).or_insert(v);
                        }
                    }
                    None => {
                        out.insert(norm, value.to_string());
                    }
                }
            }
            _ => {
                out.insert(norm, value.to_string());
            }
        }
    }
    out
}

/// Treat literal `"null"` (case-insensitive) and pure whitespace as
/// empty string. Otherwise return trimmed value.
fn denull(s: &str) -> &str {
    let t = s.trim();
    if t.is_empty() {
        return "";
    }
    if t.eq_ignore_ascii_case("null") {
        return "";
    }
    s
}

/// Parse a JSON string and flatten one level. Returns `None` when
/// the input is not parseable JSON or not a top-level object. Inner
/// non-string values are rendered via serde_json::to_string for
/// faithful round-trip.
fn flatten_json_one_level(s: &str) -> Option<Vec<(String, String)>> {
    let t = s.trim();
    if t.is_empty() {
        return None;
    }
    let parsed: serde_json::Value = serde_json::from_str(t).ok()?;
    let obj = parsed.as_object()?;
    let mut out: Vec<(String, String)> = Vec::with_capacity(obj.len());
    // Iterate in sorted key order for deterministic output.
    let mut keys: Vec<&String> = obj.keys().collect();
    keys.sort();
    for k in keys {
        let v = &obj[k];
        let s_val = match v {
            serde_json::Value::String(s) => s.clone(),
            serde_json::Value::Null => String::new(),
            other => other.to_string(),
        };
        out.push((normalize_header(k), s_val));
    }
    Some(out)
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
    fn alma_id_maps_to_external_id() {
        let r = row(&[("alma_id", "ALMA-1")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("external_id").map(String::as_str), Some("ALMA-1"));
    }

    #[test]
    fn json_in_cell_flattens_one_level() {
        let r = row(&[("extra_attributes", "{\"grade\":\"9\",\"section\":\"A\"}")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("grade").map(String::as_str), Some("9"));
        assert_eq!(out[0].get("section").map(String::as_str), Some("A"));
    }

    #[test]
    fn invalid_json_preserves_raw_cell() {
        let r = row(&[("extra_attributes", "not-json")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(
            out[0].get("extra_attributes").map(String::as_str),
            Some("not-json")
        );
    }

    #[test]
    fn null_literal_treated_as_empty() {
        let r = row(&[("email", "null")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("email").map(String::as_str), Some(""));
    }

    #[test]
    fn user_type_maps_to_role() {
        let r = row(&[("user_type", "Student")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("role").map(String::as_str), Some("Student"));
    }

    #[test]
    fn json_with_numeric_value_renders_as_string() {
        let r = row(&[("extra_attributes", "{\"score\":95}")]);
        let out = preprocess_rows(vec![r]);
        assert_eq!(out[0].get("score").map(String::as_str), Some("95"));
    }

    #[test]
    fn deterministic_output_for_same_input() {
        let r = row(&[("extra_attributes", "{\"a\":\"1\",\"b\":\"2\"}")]);
        let a = preprocess_rows(vec![r.clone()]);
        let b = preprocess_rows(vec![r]);
        assert_eq!(a, b);
    }
}
