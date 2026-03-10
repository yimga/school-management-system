# Canonical education graph

**Purpose:** Single source of truth for core education entities, relationships, ownership, source-of-truth service, and identity/deduplication rules. Use for analytics, automation, APIs, migration mapping, and "one person, one record" positioning.

---

## Canonical entities

| Entity | Owning bounded context | Source-of-truth model(s) | Source-of-truth service / API | Identity / deduplication rules |
|--------|-------------------------|---------------------------|--------------------------------|---------------------------------|
| **Person** | People & Relationships | User (accounts); base for Staff/Guardian/Student identity | people.people_management, accounts | One User per login; link to StudentProfile/TeacherProfile/GuardianProfile by school. Dedupe: email + school. |
| **Student** | People & Relationships | StudentProfile | people.people_management, people.signals (student_created) | One StudentProfile per (school, person/link). admission_number unique per school. Identity: school_id + external_id or admission_number. |
| **Guardian** | People & Relationships | GuardianProfile | people (CRUD, link_child) | One GuardianProfile per (school, User or external). Dedupe: email + school; family grouping by relationship. |
| **Staff** | People & Relationships | TeacherProfile, other staff roles | people.employer_views, people.people_management | One TeacherProfile per (school, User). Staff identity: school_id + user_id. |
| **Applicant** | Admissions | Applicant (people) | people (applicant lifecycle), schools (signup) | One Applicant per (school, application cycle). Identity: school_id + email or application_number. |
| **Enrollment** | Academics | StudentDegreeEnrollment, Section enrollment (academics) | academics (enrollment services), academics.signals (enrollment_created) | One enrollment per (student, program/section, term). Identity: student_id + section_id + academic_year. |
| **Course** | Academics | Course (academics) | academics | One Course per (school, code/name). Identity: school_id + course_id. |
| **Section** | Academics | Section / ClassSection (academics) | academics | One Section per (course, term, classroom). Identity: school_id + section_id. |
| **Attendance Event** | Academics | Attendance, TeacherAttendance | academics, people.signals (attendance_recorded) | One record per (student or teacher, date, period/session). Identity: (student_id|teacher_id) + date + session_key. Dedupe: same student/teacher + date + section. |
| **Assessment** | Academics / Evals | Evaluation, Assessment (evals) | evals | One assessment per (student, subject/term, evaluation type). Identity: student_id + evaluation_id + period. |
| **Grade Event** | Academics / Evals | Grade, marksheet (evals) | evals (grading, approval) | One grade per (student, evaluation, term). Identity: student_id + evaluation_id + term. Publish event: grade_published. |
| **Invoice** | Finance | Invoice (finance) | finance.services (create_fee_invoices), finance.signals (invoice_created) | One Invoice per (school, reference). Identity: school_id + invoice_id or reference. |
| **Payment** | Finance | Payment (finance) | finance.services (create_payment_from_receipt), finance.signals (payment_received) | One Payment per (invoice, transaction). Identity: payment_id; idempotency by reference. |
| **Communication** | Communications | Message, Announcement (communication) | communication (send, notify) | One Message per (sender, recipient(s), thread). Identity: message_id. Event: parent_notified. |
| **Intervention** | People / Academics | (Discipline, intervention, or support records as defined in people/academics) | people / academics services | One record per (student, type, date). Identity: school_id + student_id + type + date. |
| **Document** | Portal / siteconfig | Document, KB article, report output | portal (documents), reports (generate) | One document per (school, type, external_id or path). Identity: school_id + document_type + slug/id. |

---

## Relationships (explicit)

- **Person** → has many **Student**, **Guardian**, **Staff** (profiles per school).
- **Student** → has many **Enrollment**; has many **Attendance Event**; has many **Assessment** / **Grade Event**; has many **Invoice**; linked to **Guardian** (family).
- **Guardian** → has many **Student** (children); receives **Communication**; makes **Payment**.
- **Staff** → has many **Attendance Event** (teacher attendance); teaches **Section**.
- **Applicant** → may become **Student** (on admit).
- **Enrollment** → belongs to **Student**, **Section** / **Course**, **AcademicYear**.
- **Section** → belongs to **Course**, **Classroom**; has many **Enrollment**.
- **Course** → belongs to **AcademicYear** / school.
- **Attendance Event** → belongs to **Student** or **Staff**; optional **Section**.
- **Assessment** / **Grade Event** → belongs to **Student**, **Evaluation** (subject/term).
- **Invoice** → belongs to **Student** (or billing entity); has many **Payment**.
- **Payment** → belongs to **Invoice**.
- **Communication** → from/to **User** or **Guardian**/group.

---

## Ownership summary

| Context | Entities owned |
|---------|----------------|
| Identity & Access | Person (User), RBAC |
| People & Relationships | Student, Guardian, Staff, Intervention |
| Admissions | Applicant |
| Academics | Enrollment, Course, Section, Attendance Event |
| Evals (Academics) | Assessment, Grade Event |
| Finance | Invoice, Payment |
| Communications | Communication |
| Portal / Reports | Document (generated) |

---

## Mapping to existing models (reference)

- **Student** → `people.StudentProfile`
- **Guardian** → `people.GuardianProfile`
- **Staff** → `people.TeacherProfile`
- **Applicant** → `people.Applicant` (if present) / application state
- **Enrollment** → `academics.StudentDegreeEnrollment`, section enrollments
- **Course** → `academics.Course`
- **Section** → `academics` section/class models
- **Attendance Event** → `academics.Attendance`, `people.TeacherAttendance`
- **Assessment / Grade Event** → `evals.Evaluation`, grade/marksheet models
- **Invoice** → `finance.Invoice`
- **Payment** → `finance.Payment`
- **Communication** → `communication.Message`, `communication.Announcement`

---

## Use for

- **Analytics:** Aggregate by canonical entity and relationships.
- **Automation:** Trigger workflows on entity lifecycle (student_created, invoice_created, etc.).
- **APIs:** Expose stable entity names and relationships (e.g. OneRoster, Ed-Fi mapping).
- **Migration mapping:** Map source SIS to canonical entities and fields.
- **Identity resolution:** Dedupe and merge rules per entity (see table above).
- **AI grounding:** Single graph for "one person, one record" and relationship queries.
