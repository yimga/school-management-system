# Phase 7: Nice-to-Have Features Roadmap

This document lists **nice-to-have** SMS features with priority (High / Medium / Low) as defined in the critical review plan. Phases 1–6 of the plan are implemented; these items can be picked up when needed.

**Integration rule for any new feature:** Use region for dates/currency (template filters, `LocalizationService`); for Option B multi-tenant (if implemented), add `school_id` and filter by current school.

---

## High priority

| Feature | Status | What's needed |
|--------|--------|----------------|
| **SMS / WhatsApp notifications** | Partial | Integrate provider (Twilio, etc.); respect UserPreference channels and region/language for templates. |
| **Mobile app / offline** | Partial | Document PWA/offline; extend draft save if needed; ensure mobile API uses region for formatted data. |
| **Homework / assignments (student)** | Partial | Dedicated homework module: teacher assigns → student submits → grade; optional parent view. |
| **Discipline / behavior tracking** | Missing | Models and views: incidents, sanctions, reports; RBAC and optional compliance tie-in. |
| **Multi-school / group** | Option A done | Option A (separate DB per school) is documented in [MULTI_SCHOOL_ADD_NEW_SCHOOL.md](MULTI_SCHOOL_ADD_NEW_SCHOOL.md). Option B = School model, tenant FK, school-scoped config. |
| **Timetable auto-generation** | Partial | Auto-solver or UI to generate conflict-free timetable from constraints; scheduling models exist. |

---

## Medium priority

| Feature | Status | What's needed |
|--------|--------|----------------|
| **Library / resource management** | Missing | Book catalog, loans, returns, fines (region currency); optional. |
| **Video conferencing** | Partial | Complete integration with Zoom/Meet/etc.; stub in `communication/video_conferencing.py`. |
| **Analytics / BI dashboards** | Have | Improve: use region timezone and number/date format in analytics views. |

---

## Low priority

| Feature | Status | What's needed |
|--------|--------|----------------|
| **Transport / bus management** | Missing | Routes, stops, assignments; only if school runs buses. |
| **Hostel / boarding** | Missing | Rooms, occupancy, fees; only for boarding schools. |
| **Canteen / meals** | Missing | Menus, orders, payments; only if school runs canteen. |
| **Health / medical records** | Missing | Basic health records, allergies, visits; consider privacy per region. |
| **Inventory / assets** | Missing | Assets, assignments, condition; add when school requests it. |
| **Biometric / ID** | Missing | Integration with biometric/ID hardware if required. |

---

## Reference

- Plan: critical review plan (Cameroon + global flexibility).
- Phases 1–6: Foundation, region in UI, grading/reports, finance, KB (Option A), timetabling in portal.
