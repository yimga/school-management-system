"""Celery wrapper for the AI-narrated risk-digest fan-out.

WHY THIS TASK LIVES IN ITS OWN MODULE (and NOT in celery_tasks.py).

``config/celery.py`` calls a BARE ``app.autodiscover_tasks()``, which imports
only each installed app's ``tasks.py``. This task historically lived here,
isolated, so it stayed UNREGISTERED while the four compute wrappers were woken.

WOKEN 2026-08-05 (a deliberate, reviewed change). ``apps/analytics/tasks.py``
now re-exports ``send_risk_digest_task`` so its ``@shared_task`` decorator runs
and ``analytics.send_risk_digest_all`` registers. The nightly fan-out is safe to
wake because the three preconditions that kept it deferred are now met:

  1. ``send_risk_digest`` checks enabled ``RiskDigestRecipient`` rows BEFORE
     calling ``ai_narrate_risk_digest`` (the LLM gateway invoke), so per-school
     narration spend is bounded to schools that actually opted in — no more
     unbounded LLM spend for non-opted-in schools.
  2. Outbound EMAIL (real SMTP) / Slack POSTs only ever target enabled
     ``RiskDigestRecipient`` rows (per-school opt-in).
  3. The beat entry ``analytics-send-risk-digest-daily`` stays env-gated behind
     ``ENABLE_RISK_DIGEST_BEAT`` (operator opt-in per deployment).

Must-fire guards: apps/analytics/tests/test_risk_digest_recipient_gate.py (the
recipient-before-narration ordering) and
apps/analytics/tests/test_nightly_batch_task_registration.py (registration).
"""

from __future__ import annotations

from celery import shared_task

from apps.analytics.celery_tasks import _safe_call


@shared_task(name="analytics.send_risk_digest_all")
def send_risk_digest_task() -> str:
    """Fan-out the AI-narrated risk digest across every active school.

    Registered via apps/analytics/tasks.py (re-export). Narration is bounded to
    schools with an enabled RiskDigestRecipient; the beat entry is env-gated
    behind ENABLE_RISK_DIGEST_BEAT. See the module docstring.
    """
    return _safe_call("send_risk_digest")
