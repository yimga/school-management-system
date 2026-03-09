# Migration Cloud — Canonical target fields (Phase B)

**Purpose:** Single reference for target field names used by the migration wizard and schema inference. Adapters and inference align to this list.

## Students (migration_type / domain: students)

| Canonical field    | Description                    |
|--------------------|--------------------------------|
| first_name         | Given name                     |
| last_name          | Family name                    |
| admission_number   | External ID / student number   |
| academic_year      | Grade level / year             |
| classroom          | Homeroom / section             |
| specialty          | Optional                       |
| status             | Enrollment status              |

**Required:** first_name, last_name.

## Grades (migration_type / domain: grades)

| Canonical field       | Description        |
|-----------------------|--------------------|
| student_code          | Links to student   |
| subject_assignment_id | Course/section     |
| term_id               | Term               |
| teacher_username      | Optional           |
| seq1, seq2, exam, mock, practical, test1, test2 | Score columns |
| remarks               | Optional           |

**Required:** student_code, subject_assignment_id, term_id.

## Usage

- **MigrationProfile.config.target_fields** and **required** follow these names.
- **Schema hints** (adapter or inference) map source column names → these canonical names.
- See [CANONICAL_OBJECTS_MAPPING.md](CANONICAL_OBJECTS_MAPPING.md) and the Migration Cloud Strategy and Implementation Plan.
