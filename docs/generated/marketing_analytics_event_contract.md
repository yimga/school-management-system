# Marketing Analytics Event Contract

The RunMyCampus marketing analytics layer is a first-party, privacy-safe client event contract. It is no-op by default when `MARKETING_ANALYTICS_ENDPOINT_URL` is empty and does not hardcode vendor keys.

Allowed events: `page_view`, `cta_click`, `menu_open`, `menu_link_click`, `form_start`, `form_submit_attempt`, `form_submit_success`, `form_submit_error`, `pricing_plan_interest`, `resource_click`, and `scroll_milestone`.

Allowed fields: `event_name`, `page_path`, `page_type`, `page_slug`, `cta_label`, `cta_location`, `menu_name`, `link_label`, `link_target`, `form_name`, `form_stage`, `plan_name`, `resource_type`, `scroll_depth`, and `timestamp`.

The contract does not collect names, emails, phone numbers, school names, message text, student, parent, teacher, payment, CSRF, session, or tenant-private data. Unknown fields are ignored by the client sanitizer.
