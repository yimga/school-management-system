# Entity import — Column guide

## Students CSV

| Column | Required | Description |
|--------|----------|-------------|
| first_name | Yes | Student first name |
| last_name | Yes | Student last name |
| admission_number | Yes | Unique admission number |
| academic_year | Yes | Academic year ID |
| classroom | Yes | Classroom ID |
| specialty | Optional | Specialty ID |
| status | Optional | e.g. NEW, ACTIVE |

## Guardians CSV

| Column | Required | Description |
|--------|----------|-------------|
| guardian_user | Yes | User ID of guardian |
| student | Yes | Student profile ID |
| relationship | Yes | e.g. FATHER, MOTHER, GUARDIAN |
| can_view_results | Optional | true/false |
| can_view_finance | Optional | true/false |

Sample files are available from the Entity import page (Download sample).
