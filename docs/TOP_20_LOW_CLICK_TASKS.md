# Top 20 low-click tasks (BR-02)

Mapped to **command palette** (`BACKEND_COMMAND_PALETTE`) and primary CTAs. Target: ≤2 clicks from role home where feasible.

| # | Persona | Task | Entry |
|---|---------|------|-------|
| 1 | Admin | Open Studio | Palette: Studio |
| 2 | Admin | Add student | Palette: Add Student |
| 3 | Admin | Staff list | Palette: Manage Staff |
| 4 | Admin | Finance | Palette: Finance Dashboard |
| 5 | Admin | Trust / security | Palette: Trust center |
| 6 | Admin | Create school (CP) | Palette: Create school |
| 7 | Admin | Geography packs | Palette: Geography |
| 8 | Teacher | Take attendance | Palette: Take attendance |
| 9 | Teacher | My attendance hub | Palette: Teacher attendance |
| 10 | Teacher/Admin | Grade import | Palette: Import Grades |
| 11 | Teacher/Admin | At-risk students | Palette: At-risk dashboard |
| 12 | Admin | Interventions | Palette: Intervention action center |
| 13 | Admin | Publish results | Palette: Manage Exams |
| 14 | Admin | Workflow | Palette: Workflow Center |
| 15 | Admin | Experience packs | Palette: Experience |
| 16 | Admin | Documents | Quick links / portal |
| 17 | Parent | Child results | `/portal/parent/` → results |
| 18 | Parent | Attendance | Parent attendance-discipline |
| 19 | Parent | Contact school | parent_contact_school |
| 20 | Admin | SLO / health | Trust → Health / SLO dashboard |

**Code:** `apps/dashboard/action_registry.py` — extend `BACKEND_COMMAND_PALETTE` for new intents.
