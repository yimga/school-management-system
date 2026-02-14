# Messaging, Communication Module, and WhatsApp

**Purpose:** Where messaging and WhatsApp fit, how they integrate, and how to keep things simple.

---

## 1. Who Can Use What

| User type | Direct messages (1-on-1) | Group messaging | How they start contact |
|-----------|---------------------------|------------------|--------------------------|
| **Staff / Teachers** | Yes: compose, reply, close (parent threads) | Yes: Message Groups (`/communication/groups/`) | Messages → New message, or Message Groups |
| **Parents** | No — use **Contact School** form only | No | **Contact School** only (form → ContactRequest; school replies via that flow) |
| **Students** | Yes: view and reply only (threads with staff/teachers) | No | Messages (see replies when staff message them) |

- **Direct:** Staff/teachers get **Messages** → Direct tab + **New message**. **Parents do not use direct messaging**; they use **Contact School** only (sidebar → Contact School; no Messages link). Students get **Messages** → Direct tab only; they see conversations with staff and can reply when staff initiate.
- **Groups:** Only staff/teachers (and roles in `GROUP_MESSAGING_ROLES` in `apps/communication/views_groups.py`). Parents and students do not have access to Message Groups by design (keeps triage and safety in one place).

---

## 2. Where WhatsApp Integrates

WhatsApp is **not** used for in-app chat (Message/MessageThread). It is used for **notifications and outbound contact** only.

| Area | How WhatsApp is used | Code / config |
|------|----------------------|----------------|
| **Payment reminders** | Optional channel (with email/SMS). Sends reminder text via link or API. | `apps/finance/tasks.py`, `PaymentReminder.channels`, `SiteSettings.finance_payment_reminder_default_channels`, `finance_payment_reminder_enable_whatsapp` |
| **Report sharing** | Parent taps “Share via WhatsApp”; opens `wa.me` with report link (user-initiated, no API). | `SiteSettings.enable_whatsapp_parent_portal`, report share view |
| **Contact / support** | Footer and portal “Chat on WhatsApp” = link to `wa.me` with school number. | `SiteSettings.whatsapp_support_number`, `enable_whatsapp_parent_portal`, `enable_whatsapp_staff_portal`; `apps/portal/services.py` `_communication_center()` |
| **Integrations (optional)** | If you use **WhatsApp Business API**, `apps/communication/integrations.py` has `WhatsAppIntegration` and `CommunicationService` to send template/text messages. | `WHATSAPP_API_TOKEN`, `WHATSAPP_API_URL`; not required for wa.me flows |
| **Evals / notifications** | Deeplinks only: build `wa.me` URL for a phone + message; no API send. | `apps/evals/notifications.py` `send_whatsapp()` (link generation) |

So: **in-app messaging** = Messages (direct) + Message Groups. **WhatsApp** = notifications, payment reminders, report sharing, and support links. They are separate; we are not complicating in-app chat with WhatsApp.

---

## 3. Simplification and Efficiency

**What we kept simple:**

- **One Messages hub** for staff/teachers: Direct + Groups in one place. Parents and students have one place (Messages) for direct threads only; no Groups.
- **Contact School** remains the single way for parents to **start** a new request (form → ContactRequest). Replies from school appear in Messages → Direct so parents don’t have to look in two places.
- **WhatsApp** is either:
  - **Free:** wa.me links (report share, support, payment reminder link in finance tasks) + optional SiteSettings flags.
  - **Paid (optional):** WhatsApp Business API in `communication/integrations.py` for automated sends; only needed if you want API-driven WhatsApp messages.

**Efficiency improvements you can make without adding features:**

- **Payment reminders:** Rely on one or two channels (e.g. email + WhatsApp link) and cap reminder frequency; avoid turning on every channel (email + SMS + WhatsApp API) unless needed.
- **Contact School:** Keep one triage flow (ContactRequest → assign → reply). Parents use this only; they do not have a Messages/direct inbox.
- **Group messaging:** Keep it staff-only; don’t add parent/student to Message Groups unless you have a clear need (e.g. class broadcast), and then use a single pattern (e.g. class-level thread with clear rules).

**Avoid:**

- Using WhatsApp as the transport for in-app Message/Thread content (double storage, sync, and policy issues). Keep in-app chat in the DB; use WhatsApp only for notifications and links.
- Adding more “communication” entry points (e.g. separate “Parent WhatsApp inbox”). Prefer: Messages for staff/students; Contact School only for parents; WhatsApp for links/reminders.

---

## 4. File References

| Topic | Files |
|-------|--------|
| Direct messaging (views, permissions) | `apps/accounts/views.py` (`user_messages`, `direct_thread`, `direct_compose`, `_can_access_direct_messages`, `_direct_conversations`) |
| Group messaging (permissions, views) | `apps/communication/views_groups.py` (`_can_access_group_messaging`, `group_list`, `group_detail`) |
| Contact School (parent form) | `apps/portal/views_contact_requests.py` (`parent_contact_school`), `templates/parent/contact_school.html` |
| Sidebar (Messages / Contact School) | `apps/siteconfig/portal_sidebar_items.py` |
| WhatsApp Business API (optional) | `apps/communication/integrations.py` (`WhatsAppIntegration`, `CommunicationService`) |
| WhatsApp deeplinks (evals) | `apps/evals/notifications.py` (`send_whatsapp`) |
| Payment reminders (channels) | `apps/finance/tasks.py`, `apps/finance/models.py` (`PaymentReminder`), `SiteSettings` (finance_*_whatsapp, channels) |
| WhatsApp opt-in and channels | `docs/WHATSAPP_OPT_IN.md`, `apps/automation/helpers.py` (`get_notification_channels`) |

---

## 5. Summary

- **Group and direct messaging** work for all non-parent users: staff/teachers get full Direct + Groups; students get Direct only (view/reply with staff). Parents use **Contact School** only, no direct messaging.
- **WhatsApp** integrates only for notifications, payment reminders, report sharing, and support links—not for in-app chat. That keeps the model simple and avoids duplicating chat in WhatsApp.
- To keep things efficient and simple: use one Messages hub, one Contact School flow, and limit WhatsApp to the channels you actually use (e.g. wa.me links first; add API only if needed).

---

## 6. Making Better Use of WhatsApp (While Keeping It Simple)

Almost everyone uses WhatsApp. You can get most of the benefit **without** the WhatsApp Business API—using **wa.me links** and a single school number. Keep one source of truth and surface it everywhere it helps.

### One config to rule them all

- Set **Site Settings → WhatsApp support number** (e.g. `+23761234567`) and turn on **Enable WhatsApp (Parent Portal)** and, if you want, **Enable WhatsApp (Staff Portal)**.
- That number is used for: footer “WhatsApp Support”, parent dashboard and Contact School “WhatsApp Support”, Communication Center “Chat on WhatsApp”, and (when enabled) payment reminder links. No need to create a separate Integration unless you use the API.
- Optionally set **WhatsApp admissions number** for a second line (e.g. admissions); parents then see Support + Admissions.

### Where WhatsApp already appears (use it well)

| Place | What to do |
|-------|------------|
| **Contact School** | When enabled, parents see “WhatsApp Support” and “Admissions WhatsApp”. Keep it visible so parents can choose form or WhatsApp. |
| **Parent dashboard** | Same buttons; low friction for “quick question”. |
| **Footer** | One “WhatsApp Support” pill; same number. |
| **Report sharing** | “Share via WhatsApp” sends the report link; parent shares with family. No extra config. |
| **Payment reminders** | In Finance, enable WhatsApp in default channels and in reminder config; guardians who opt in get a wa.me link (or API message if you use the API). Prefer **one or two** channels (e.g. email + WhatsApp) so reminders are effective, not noisy. |
| **Staff: Contact request detail** | When viewing a parent’s request, staff see a “Chat on WhatsApp” link using the parent’s number—great for quick follow-up. |

### Small improvements that stay simple

- **Communication Center:** If you don’t use an Integration, the app now falls back to **Site Settings** (support number or footer WhatsApp URL) so “Chat on WhatsApp” still appears. One config is enough.
- **Guardian phone/WhatsApp:** Ensure guardian and parent profiles store **WhatsApp number** (and that link-child and onboarding collect it). Then payment reminders and staff “reply via WhatsApp” work without extra steps.
- **Default channels:** If most of your community uses WhatsApp, set default notification channels to include `whatsapp` (e.g. `["email", "whatsapp"]`) so reminders and key notices can go there; users can still opt out in Preferences.

### What not to do (keeps things simple)

- **Don’t add an WhatsApp “inbox”** in the app. Conversations stay on WhatsApp; staff use the app for Contact School triage and for “open in WhatsApp” links.
- **Don’t enable the API** unless you need automated sending (e.g. bulk reminders). wa.me links are free and enough for support, follow-up, and report sharing.
- **Don’t duplicate in-app messages to WhatsApp.** Keep Messages/Contact School as the single place for school–parent thread history; use WhatsApp for live chat and links only.
