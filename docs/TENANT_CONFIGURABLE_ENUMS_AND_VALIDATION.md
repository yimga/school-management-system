# Tenant-configurable enums and validation rules (W3-1, W3-2)

## Configurable enum choices (W3-1)

Schools can override or extend key dropdown choices via **School.settings** JSON. The helper `get_tenant_enum_choices(school, key)` in `apps/siteconfig/tenant_config.py` returns a list of `(value, label)` tuples.

### Supported keys

| Key | Default source | Use in |
|-----|----------------|--------|
| `relationship_choices` | `PendingGuardianInvite.Relationship.choices` | Guardian/parent relationship dropdown |
| `student_status_choices` | `StudentProfile.Status.choices` | Student status (New, Returning, Alumni, etc.) |
| `dashboard_view_choices` | `TeacherProfile.DashboardView.choices` | Teacher default dashboard view (Overview, Finance, etc.) |

### Format in School.settings

```json
{
  "relationship_choices": [
    ["MOTHER", "Mother"],
    ["FATHER", "Father"],
    ["GUARDIAN", "Guardian"],
    ["SPONSOR", "Sponsor"]
  ],
  "student_status_choices": [
    ["NEW", "New"],
    ["RETURNING", "Returning"],
    ["ALUMNI", "Alumni"]
  ],
  "dashboard_view_choices": [
    ["OVERVIEW", "Overview"],
    ["WORKFLOW", "Workflow Center"]
  ]
}
```

Each value can also be `{"value": "X", "label": "Y"}`. If the list is missing or empty, model defaults are used.

### Usage in code

```python
from apps.siteconfig.tenant_config import get_tenant_enum_choices

school = request.school
choices = get_tenant_enum_choices(school, "relationship_choices")
# Use in form: form.fields["relationship"].choices = choices
```

---

## Validation & rules (W3-2)

Validation rules are read from **School.settings** via `get_tenant_validation_rules(school)` in `apps/siteconfig/tenant_config.py`.

### Keys

| Key | Description | Default |
|-----|-------------|--------|
| `admission_pattern` | Regex for admission number format | `^[A-Z0-9\-]+$` |
| `file_max_size_mb` | Max upload size in MB | `10` |
| `allowed_file_types` | List of allowed extensions (e.g. pdf, jpg) | `["pdf", "jpg", "jpeg", "png"]` |
| `phone_regex` | Regex for phone validation | `^\+?[\d\s\-()]{8,20}$` |
| `refund_reasons` | List of refund reason codes/labels or free text | `[]` |

### Example School.settings

```json
{
  "admission_pattern": "^ADM-[0-9]{4}$",
  "file_max_size_mb": 5,
  "allowed_file_types": ["pdf", "jpg", "png", "doc", "docx"],
  "phone_regex": "^\\+237[0-9]{8}$",
  "refund_reasons": ["DUPLICATE", "WITHDRAWAL", "OTHER"]
}
```

### Usage

- **Admission number:** In student create/edit or import, validate `admission_number` against `rules["admission_pattern"]` (e.g. `re.match(rules["admission_pattern"], value)`).
- **File uploads:** Check file size against `rules["file_max_size_mb"] * 1024 * 1024` and extension against `rules["allowed_file_types"]`.
- **Phone:** Validate phone fields with `rules["phone_regex"]`.
- **Refund:** Use `rules["refund_reasons"]` in finance refund form or API.

Implementors should call `get_tenant_validation_rules(request.school)` (or the current school) and apply these in the relevant forms and serializers.
