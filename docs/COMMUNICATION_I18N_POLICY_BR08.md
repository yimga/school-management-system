# Communication + i18n (BR-08)

## Policy

- **Retention:** `school.settings.comms_thread_retention_days` (default **730**). Run `python manage.py purge_thread_message_retention` (optional `--school-id`, `--dry-run`) on a schedule; soft-deletes old `ThreadMessage` rows.
- **Translation:** `locale_target_for_user(recipient)` on **`Message`** everywhere: `accounts` DM, `communication.api_views` (single + bulk), `portal.views_support` / `views_student`, `requests.services.notify_requester`, `finance.views_access`. Group threads: `ThreadMessage` in `views_groups`. Machine translation: `comms_auto_translate` (provider TBD).
- **Audit:** High-sensitivity threads logged to compliance audit where configured.

## Product direction

- In-app **ThreadMessage** remains SoR; Remind-class blast = `communication` broadcast modules.
- **Bi-directional translate:** Phase 2 — integrate provider when budget approved.
