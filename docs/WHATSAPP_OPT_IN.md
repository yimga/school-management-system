# WhatsApp Opt-in and Notification Channels

**Purpose:** How WhatsApp is enabled at site level and how users opt in or out of WhatsApp (and other channels) for notifications.

---

## 1. Site-level enablement

- **Parent portal:** `SiteSettings.enable_whatsapp_parent_portal` — when True, WhatsApp options appear in the parent portal (e.g. Share report via WhatsApp, payment reminders can use WhatsApp if selected).
- **Staff portal:** `SiteSettings.enable_whatsapp_staff_portal` — when True, staff can use WhatsApp for relevant notifications.
- **Payment reminders:** `SiteSettings.finance_payment_reminder_default_channels` — list of default channels (e.g. `["email", "whatsapp"]`). When WhatsApp is in this list and enabled for the portal, reminders can be sent via WhatsApp to users who have opted in.

---

## 2. Per-user opt-in (UserPreference)

- **Model:** `UserPreference.notification_channels` (JSONField, list of channel codes).
- **Choices:** `UserPreference.NotificationChannel`: EMAIL, SMS, APP, WHATSAPP.
- **Where to set:** User **Preferences** (staff: via Preferences in the backend/sidebar; or admin-edited UserPreference). Users select which channels they want (e.g. Email + WhatsApp).
- **Behaviour:** `get_notification_channels(user, automation_type)` in `apps/automation/helpers.py` returns:
  1. **UserPreference.notification_channels** if set (full opt-in/opt-out per user).
  2. Else SiteSettings default for that automation type (e.g. `finance_payment_reminder_default_channels`).
  3. Else system default `["email"]`.

So: **opt-in = user selects WhatsApp in Preferences**. If the user leaves notification_channels empty, site defaults are used (so enabling WhatsApp in Site Settings + default channels effectively opts everyone in unless they override in Preferences).

---

## 3. Report sharing via WhatsApp

- On the **Share Report** page (after “Share Term Report” / “Share Annual Report”), a **Share via WhatsApp** button is shown when `SiteSettings.enable_whatsapp_parent_portal` is True.
- The button opens `https://wa.me/?text=<share_url>` so the parent can send the secure report link via WhatsApp. No separate opt-in needed for this action (user-initiated share).

---

## 4. Summary

| What | Where | Opt-in behaviour |
|------|--------|-------------------|
| Payment reminders (email/SMS/WhatsApp) | Site Settings: default channels; UserPreference: per-user channels | UserPreference overrides site default; user can include or exclude WhatsApp. |
| Report share link via WhatsApp | Share Report page | Button shown when parent WhatsApp enabled; user chooses to click. |
| Other automations (deadline reminders, etc.) | Same `get_notification_channels()` | Same: UserPreference first, then SiteSettings, then email. |

To **opt out** of WhatsApp: user clears WhatsApp from their Preferences notification channels, or sets only Email (and optionally SMS). To **opt in**: user adds WhatsApp in Preferences (when site has WhatsApp enabled).
