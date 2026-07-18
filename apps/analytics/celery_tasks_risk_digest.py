"""Deferred Celery wrapper for the AI-narrated risk-digest fan-out.

WHY THIS TASK LIVES IN ITS OWN MODULE (and NOT in celery_tasks.py).

``config/celery.py`` calls a BARE ``app.autodiscover_tasks()``, which imports
only each installed app's ``tasks.py``. ``apps/analytics/tasks.py`` re-exports
the FOUR safe nightly COMPUTE wrappers from ``celery_tasks.py`` so their
``@shared_task`` decorators run and their beat entries resolve. It deliberately
does NOT import THIS module, so ``analytics.send_risk_digest_all`` stays
UNREGISTERED — a deferred beat entry recorded in
``scripts/verify_beat_task_registry.py::KNOWN_DEAD_ENTRIES``.

Importing a module runs ALL of its ``@shared_task`` decorators, so isolating
this one in a module nothing imports is the only way to wake the four compute
tasks WITHOUT waking this one as a side effect.

WHY IT IS DEFERRED (not woken). ``send_risk_digest`` does two
externally-visible things per nightly run, fanned out over EVERY active school:

  1. It calls ``ai_narrate_risk_digest`` — an LLM gateway invoke
     (``services.ai_helpers.invoke_with_request``, task_type
     ``OBSERVABILITY_NARRATIVE``) — for every active school that has fresh
     RiskFactor rows, BEFORE it checks whether that school has configured any
     digest recipient. So enabling it incurs unbounded LLM spend even for
     schools that never opted into the digest.
  2. For schools that DO have enabled ``RiskDigestRecipient`` rows, it sends
     outbound EMAIL (real SMTP) and POSTs to Slack webhooks.

Waking it by a code-registration side effect would send real outbound mail /
Slack AND run per-school LLM narration platform-wide the moment an operator sets
``ENABLE_RISK_DIGEST_BEAT=1``. That is the same "real but dangerous to wake"
class as the migration-cloud webhook/smoke KNOWN_DEAD entries.

TO WAKE IT SAFELY (a deliberate, reviewed change — NOT a drive-by import):
  * Move the ``RiskDigestRecipient`` check BEFORE ``_generate_digest`` in
    ``apps/analytics/management/commands/send_risk_digest.py`` so narration only
    runs for schools that actually have an enabled recipient (bounds LLM spend);
  * re-export ``send_risk_digest_task`` from ``apps/analytics/tasks.py`` (next to
    the four compute wrappers); and
  * remove ``analytics-send-risk-digest-daily`` from KNOWN_DEAD_ENTRIES.
"""

from __future__ import annotations

from celery import shared_task

from apps.analytics.celery_tasks import _safe_call


@shared_task(name="analytics.send_risk_digest_all")
def send_risk_digest_task() -> str:
    """Fan-out the AI-narrated risk digest across every active school.

    DEFERRED: not registered by autodiscovery — this module is imported nowhere.
    See the module docstring for the (deliberate) wake procedure.
    """
    return _safe_call("send_risk_digest")
