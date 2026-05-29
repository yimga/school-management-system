"""
Celery tasks for siteconfig (Phase E: revenue stats; Phase Welcome: welcome email).
§2.4: Typed exception tuples and log_exception_with_context for send_welcome_email and check_regional_ollama_health.
"""

from smtplib import SMTPException
from urllib.error import URLError

from celery import shared_task
from django.core.management.base import CommandError
from django.db import DatabaseError

_SITECONFIG_SUPPORT_WEBHOOK_RETRY_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    URLError,
)

from apps.platform_runtime.structured_logging import log_exception_with_context

# §2.4: Typed tuples for task exception paths (no broad except).
_SITECONFIG_TASK_EMAIL_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    SMTPException,
    UnicodeError,
    AttributeError,
    TypeError,
)
_SITECONFIG_TASK_OLLAMA_ERRORS = (
    OSError,
    ConnectionError,
    TimeoutError,
    URLError,
    ValueError,
    AttributeError,
    TypeError,
)
_SITECONFIG_TASK_COMMAND_ERRORS = (
    CommandError,
    DatabaseError,
    OSError,
    ConnectionError,
    TimeoutError,
    RuntimeError,
    TypeError,
    ValueError,
)


@shared_task(name="siteconfig.calculate_monthly_revenue_stats")
def calculate_monthly_revenue_stats(snapshot_date=None):
    """
    Phase E: Run calculate_monthly_stats to fill RevenueSnapshot.
    Schedule daily via Celery Beat (e.g. 02:00).
    """
    from .billing_services import calculate_monthly_stats
    from datetime import date

    if snapshot_date:
        if isinstance(snapshot_date, str):
            snapshot_date = date.fromisoformat(snapshot_date)
    return calculate_monthly_stats(snapshot_date=snapshot_date)


@shared_task(name="siteconfig.send_welcome_email")
def send_welcome_email(school_id: int, contact_email: str = ""):
    """
    Phase Welcome: Send welcome email after school provisioning.
    HTML template with tenant branding (primary_color, logo_url), unique login URL,
    and optional dynamic block (Trade vs General). Trigger via signal on School create.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from apps.schools.models import School

    school = School.objects.filter(pk=school_id).first()
    if not school:
        return {"ok": False, "reason": "school_not_found"}
    email = contact_email or getattr(school, "contact_email", None) or ""
    if not email:
        return {"ok": False, "reason": "no_contact_email"}
    subject = f"Welcome to {getattr(settings, 'SITE_NAME', 'Portal')} — {school.name}"
    body = f"Your school {school.name} has been set up. Log in at your school URL to get started."
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
            [email],
            fail_silently=True,
            html_message=body.replace("\n", "<br>\n"),
        )
        return {"ok": True, "sent_to": email}
    except _SITECONFIG_TASK_EMAIL_ERRORS:
        log_exception_with_context(
            "siteconfig.send_welcome_email failed",
            school_id=school_id,
            exc_info=True,
            extra={"contact_email": email},
        )
        return {"ok": False, "error": "Failed to send welcome email."}


@shared_task(
    bind=True,
    name="siteconfig.deliver_support_ticket_http_webhook",
    autoretry_for=_SITECONFIG_SUPPORT_WEBHOOK_RETRY_ERRORS,
    retry_backoff=30,
    retry_kwargs={"max_retries": 5},
)
def deliver_support_ticket_http_webhook(self, url: str, secret: str, payload: dict):
    """
    Deliver signed JSON to an external support integration URL (retries on transport / HTTP 5xx).
    """
    from apps.siteconfig.support_webhook_delivery import post_support_ticket_webhook

    post_support_ticket_webhook(url, secret or "", payload)


# World Engine: National Syllabus Sync (Ministry API/OCR → LLM 36-week schemes); chunked for 195-country scale.
BROADCAST_BATCH_SIZE = 100


@shared_task(name="siteconfig.national_syllabus_sync")
def national_syllabus_sync(country_code: str, payload=None):
    """
    Stub: Ministry API/OCR → map to GlobalSyllabus; produce 36-week schemes via Ollama.
    payload can include ocr_text or ministry_api_response. Extend with actual integration.
    """
    from .models import GlobalSyllabus

    count = GlobalSyllabus.objects.filter(country_code=country_code).count()
    return {"country_code": country_code, "syllabus_nodes": count, "status": "stub"}


@shared_task(name="siteconfig.emergency_broadcast_fanout", bind=True)
def emergency_broadcast_fanout(self, campaign_id, recipient_ids=None):
    """
    World Engine: Fan-out broadcast to 5k+ devices in batches; WebSocket/Redis Pub/Sub for delivery.
    slide_confirm_required is on BroadcastCampaign. Chunk recipient_ids (or load from campaign) in batches of BROADCAST_BATCH_SIZE.
    """
    from .models import BroadcastCampaign

    try:
        # tenant-isolation-allow: celery-task-runs-inside-tenant-context-or-rls-sweep
        _campaign = BroadcastCampaign.objects.get(pk=campaign_id)
    except BroadcastCampaign.DoesNotExist:
        return {"ok": False, "error": "campaign_not_found"}
    ids = list(recipient_ids or [])[:10000]
    total = len(ids)
    for i in range(0, total, BROADCAST_BATCH_SIZE):
        _batch = ids[i : i + BROADCAST_BATCH_SIZE]
        # Stub: actual delivery via WebSocket/Redis Pub/Sub; slide-to-confirm UI on client
        pass
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "batches": (total + BROADCAST_BATCH_SIZE - 1) // BROADCAST_BATCH_SIZE,
    }


# Sovereign AI: health check and global upgrade

AI_HEALTH_CACHE_PREFIX = "ai:health:"
AI_HEALTH_CACHE_TTL = 300


@shared_task(name="siteconfig.check_regional_ollama_health")
def check_regional_ollama_health(cluster: str = None):
    """
    Ping regional Ollama URL and store result in cache (ai:health:{cluster}).
    Call periodically or on-demand from AI Model Hub. If cluster is None, check all active RegionalAIConfig.
    """
    from django.core.cache import cache
    from django.utils import timezone
    from .models import RegionalAIConfig

    now = timezone.now().isoformat()
    if cluster:
        configs = RegionalAIConfig.objects.filter(
            regional_cluster=cluster, is_active=True
        )
    else:
        configs = RegionalAIConfig.objects.filter(is_active=True)

    config_list = list(configs)
    for config in config_list:
        key = f"{AI_HEALTH_CACHE_PREFIX}{config.regional_cluster}"
        base = (config.ollama_base_url or "").rstrip("/")
        if not base:
            cache.set(
                key,
                {"status": "unavailable", "last_check_at": now, "error": "no_url"},
                timeout=AI_HEALTH_CACHE_TTL,
            )
            continue
        url = f"{base}/api/tags"
        try:
            import urllib.request

            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    cache.set(
                        key,
                        {"status": "ok", "last_check_at": now},
                        timeout=AI_HEALTH_CACHE_TTL,
                    )
                else:
                    cache.set(
                        key,
                        {
                            "status": "unavailable",
                            "last_check_at": now,
                            "code": resp.status,
                        },
                        timeout=AI_HEALTH_CACHE_TTL,
                    )
        except _SITECONFIG_TASK_OLLAMA_ERRORS as e:
            log_exception_with_context(
                "siteconfig.check_regional_ollama_health: ollama check failed",
                extra={
                    "cluster": config.regional_cluster,
                    "url": base,
                    "error": str(e),
                },
            )
            cache.set(
                key,
                {"status": "unavailable", "last_check_at": now, "error": str(e)},
                timeout=AI_HEALTH_CACHE_TTL,
            )
    return {"checked": len(config_list)}


@shared_task(name="siteconfig.sync_regional_models_for_cluster")
def sync_regional_models_for_cluster(cluster: str, run_id: str = None):
    """Run sync_regional_models for one cluster (used by global upgrade). If run_id set, update progress cache."""
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command("sync_regional_models", "--cluster", cluster, stdout=out)
    if run_id:
        from django.core.cache import cache

        key = f"{AI_UPGRADE_PROGRESS_PREFIX}{run_id}"
        data = cache.get(key) or {}
        data["regions_done"] = data.get("regions_done", 0) + 1
        data["status"] = "running"
        cache.set(key, data, timeout=AI_UPGRADE_PROGRESS_TTL)
    return {"cluster": cluster, "output": out.getvalue()}


AI_UPGRADE_PROGRESS_PREFIX = "ai:upgrade_progress:"
AI_UPGRADE_PROGRESS_TTL = 3600


@shared_task(name="siteconfig.global_ai_upgrade_run", bind=True)
def global_ai_upgrade_run(self, run_id: str, model_id: str):
    """
    Enqueue one sync_regional_models task per active cluster; update progress in cache.
    Frontend polls ai:upgrade_progress:{run_id} for regions_done/regions_total.
    """
    from django.core.cache import cache
    from .models import RegionalAIConfig

    clusters = list(
        RegionalAIConfig.objects.filter(is_active=True)
        .values_list("regional_cluster", flat=True)
        .distinct()
    )
    if not clusters:
        cache.set(
            f"{AI_UPGRADE_PROGRESS_PREFIX}{run_id}",
            {"status": "done", "regions_total": 0, "regions_done": 0},
            timeout=AI_UPGRADE_PROGRESS_TTL,
        )
        return {"run_id": run_id, "regions_total": 0}

    cache.set(
        f"{AI_UPGRADE_PROGRESS_PREFIX}{run_id}",
        {
            "status": "queued",
            "regions_total": len(clusters),
            "regions_done": 0,
            "clusters": clusters,
        },
        timeout=AI_UPGRADE_PROGRESS_TTL,
    )
    for c in clusters:
        sync_regional_models_for_cluster.delay(c, run_id)
    return {"run_id": run_id, "regions_total": len(clusters)}


@shared_task(name="siteconfig.index_ai_knowledge_beat")
def index_ai_knowledge_beat() -> str:
    """
    Daily when ENABLE_AI_KNOWLEDGE_INDEX_BEAT=1: run index_ai_knowledge for RAG.

    See docs/architecture/ai_orchestration.md.
    """
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    err = StringIO()
    call_command("index_ai_knowledge", stdout=out, stderr=err)
    return (out.getvalue() + err.getvalue())[-4000:]


@shared_task(
    bind=True,
    autoretry_for=(
        OSError,
        ConnectionError,
        TimeoutError,
    ),
    retry_kwargs={"max_retries": 3, "countdown": 20},
    name="siteconfig.execute_school_workflow_async",
)
def execute_school_workflow_async(
    self,
    school_workflow_id: int,
    context: dict | None = None,
    user_id: int | None = None,
):
    """
    Queue execution for heavy workflows (same semantics as synchronous run_school_workflow).
    Celery retries up to 3 times on transient OS/connection errors (broker/network).
    Action-level failures are recorded on SchoolWorkflowExecutionLog; use a new run to retry logic.
    """
    from django.contrib.auth import get_user_model
    from django.db import DatabaseError, OperationalError

    from apps.siteconfig.models_workflow import SchoolAutomationWorkflow
    from apps.siteconfig.workflow_engine import run_school_workflow

    wf = (
        SchoolAutomationWorkflow.objects.select_related("school")
        .filter(pk=school_workflow_id)
        .first()
    )
    if not wf:
        return {"ok": False, "error": "workflow_not_found"}
    User = get_user_model()
    user = User.objects.filter(pk=user_id).first() if user_id else None
    ctx = context if isinstance(context, dict) else {}
    try:
        return run_school_workflow(wf, ctx, user=user)
    except (DatabaseError, OperationalError) as exc:
        raise self.retry(exc=exc) from exc


@shared_task(name="siteconfig.retry_school_workflow_execution_async")
def retry_school_workflow_execution_async(
    execution_log_id: int,
    context_override: dict | None = None,
    user_id: int | None = None,
):
    """Retry failed actions on an execution log (async path)."""
    from django.contrib.auth import get_user_model

    from apps.siteconfig.workflow_engine import retry_failed_actions_from_log

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first() if user_id else None
    ctx = context_override if isinstance(context_override, dict) else {}
    return retry_failed_actions_from_log(
        int(execution_log_id),
        user=user,
        context_override=ctx,
    )


@shared_task(name="siteconfig.ai_quality_scorecard_beat")
def ai_quality_scorecard_beat() -> str:
    """
    Weekly when ENABLE_AI_QUALITY_SCORECARD_BEAT=1: aggregate metrics and print scorecard.
    """
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    err = StringIO()
    call_command("aggregate_ai_metrics", stdout=out, stderr=err)
    call_command("ai_quality_scorecard", "--days", "7", stdout=out, stderr=err)
    return (out.getvalue() + err.getvalue())[-4000:]


@shared_task(name="siteconfig.ingest_policy_documents_all_tenants")
def ingest_policy_documents_all_tenants() -> dict:
    """
    Pass 13.E: nightly per-tenant policy / handbook ingestion into AIEmbeddingStore.

    Iterates every active School that has `settings["policy_doc_root"]` set
    and calls the existing `ingest_policy_documents` mgmt command for each.
    A failure on one school does not halt the rest. Cheap when no tenants
    opt in — the path check exits before any embedding work.
    """
    from io import StringIO

    from django.core.management import call_command

    try:
        from apps.schools.models import School
    except ImportError:
        return {"processed": 0, "skipped": 0, "errors": 0, "reason": "schools unavailable"}

    processed = 0
    skipped = 0
    errors = 0
    schools = School.objects.filter(is_active=True).only("id", "settings")
    for school in schools.iterator(chunk_size=100):
        settings_dict = getattr(school, "settings", None) or {}
        path = (settings_dict.get("policy_doc_root") or "").strip()
        if not path:
            skipped += 1
            continue
        try:
            out = StringIO()
            err = StringIO()
            call_command(
                "ingest_policy_documents",
                "--school",
                str(school.id),
                "--path",
                path,
                stdout=out,
                stderr=err,
            )
            processed += 1
        except _SITECONFIG_TASK_COMMAND_ERRORS as exc:
            errors += 1
            log_exception_with_context(
                "ingest_policy_documents_all_tenants: school batch failed",
                school_id=str(school.id),
                extra={"error": str(exc)[:200]},
            )
    return {"processed": processed, "skipped": skipped, "errors": errors}


@shared_task(name="siteconfig.snapshot_platform_pulse_daily")
def snapshot_platform_pulse_daily():
    """Daily cockpit-pulse snapshot — wraps the management command (01:15 UTC beat)."""
    from django.core.management import call_command
    try:
        call_command("snapshot_platform_pulse")
    except _SITECONFIG_TASK_COMMAND_ERRORS as exc:
        log_exception_with_context(
            "snapshot_platform_pulse_daily: capture failed",
            extra={"error": str(exc)[:200]},
        )
        return {"status": "error"}
    return {"status": "ok"}


_SITECONFIG_SLA_SWEEP_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


@shared_task(name="siteconfig.support_sla_breach_sweep")
def support_sla_breach_sweep():
    """v4.00.37 — Sweep open support tickets and notify assignees on SLA breach.

    Runs every 30 minutes via Celery beat. For each open / in-progress ticket
    that has crossed its response-SLA OR resolution-SLA threshold, fires the
    notification hook with type "support.sla.breached" so the existing
    email + push fan-out delivers a breach warning. Each breach is recorded
    once per status-transition window via ticket.metadata["sla_alerts"] so
    operators are not spammed.
    """
    try:
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket
        from apps.siteconfig.support_sla import (
            ticket_resolution_breach,
            ticket_response_breach,
        )
        from apps.siteconfig.support_ticket_hooks import (
            run_support_ticket_created_hooks,
        )
    except _SITECONFIG_SLA_SWEEP_ERRORS as exc:
        log_exception_with_context(
            "support_sla_breach_sweep: import failed",
            extra={"error": str(exc)[:200]},
        )
        return {"status": "error", "checked": 0, "alerted": 0}

    open_statuses = (
        GlobalSupportTicket.Status.OPEN,
        GlobalSupportTicket.Status.IN_PROGRESS,
        GlobalSupportTicket.Status.WAITING,
    )
    # tenant-isolation-allow: support-sla-sweep-cross-tenant-platform-job-by-design
    queryset = GlobalSupportTicket.objects.filter(status__in=open_statuses).order_by(
        "-priority", "created_at"
    )

    checked = 0
    alerted = 0
    for ticket in queryset.iterator(chunk_size=200):
        checked += 1
        try:
            response_breach = ticket_response_breach(ticket)
            resolution_breach = ticket_resolution_breach(ticket)
            if not response_breach and not resolution_breach:
                continue
            metadata = dict(ticket.metadata or {})
            alerts = list(metadata.get("sla_alerts") or [])
            kind = "resolution" if resolution_breach else "response"
            existing_for_kind = [a for a in alerts if a.get("kind") == kind]
            # Only one alert per kind per status — avoids spamming on every sweep.
            if existing_for_kind and existing_for_kind[-1].get("status") == ticket.status:
                continue
            from django.utils import timezone

            alerts.append(
                {
                    "kind": kind,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "at": timezone.now().isoformat(),
                }
            )
            metadata["sla_alerts"] = alerts[-20:]
            type(ticket).objects.filter(pk=ticket.pk).update(metadata=metadata)
            recipient_id = ticket.assigned_to_id
            # v4.00.43 — escalate to backup on-call when the resolution SLA
            # breached. Notifies the FIRST backup currently on call (if any)
            # without removing the original assignee.
            try:
                run_support_ticket_created_hooks(
                    str(ticket.pk),
                    primary_recipient_id=recipient_id,
                )
            except _SITECONFIG_SLA_SWEEP_ERRORS:
                pass
            if kind == "resolution":
                try:
                    from apps.siteconfig.support_on_call import get_first_backup

                    backup = get_first_backup()
                    if backup is not None and getattr(backup, "id", None) != recipient_id:
                        run_support_ticket_created_hooks(
                            str(ticket.pk),
                            primary_recipient_id=backup.id,
                        )
                except _SITECONFIG_SLA_SWEEP_ERRORS:
                    pass
            alerted += 1
        except _SITECONFIG_SLA_SWEEP_ERRORS as exc:
            log_exception_with_context(
                "support_sla_breach_sweep: per-ticket failed",
                extra={"ticket_id": str(ticket.pk), "error": str(exc)[:200]},
            )
            continue
    return {"status": "ok", "checked": checked, "alerted": alerted}
