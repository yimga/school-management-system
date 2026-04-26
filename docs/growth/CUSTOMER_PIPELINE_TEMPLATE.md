# Customer pipeline template (Copy to spreadsheet; optional `/sales/` in app)

| Column | Description |
|--------|-------------|
| **id** | Optional row id |
| **school_name** | Institution or trust name |
| **contact** | Primary contact name |
| **email** | Work email |
| **phone** | Optional |
| **role** | Head / IT / Ops / Bursar |
| **student_count** | Integer band (e.g. 200–500) |
| **campuses** | 1 / 2 / many |
| **pain** | 1 line (visibility, comms, reporting) |
| **stage** | identified · contacted · demo_booked · demo_done · pilot_offered · onboarding · active · lost |
| **next_action** | 1 line |
| **next_follow_up** | Date |
| **source** | LinkedIn, referral, event |
| **notes** | Free text (short) |

**Optional:** If you use the in-repo pipeline (`apps.sales` on the **manager** host at `/sales/`), mirror **stages** and **next_follow_up** there for operators with control-plane access—still **no** external CRM integration.

## Related

- `OUTREACH_PLAYBOOK.md` · `GTM_HANDOFF.md`
