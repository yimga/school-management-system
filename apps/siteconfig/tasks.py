"""
Celery tasks for siteconfig (Phase E: revenue stats; Phase Welcome: welcome email).
§2.4: Typed exception tuples and log_exception_with_context for send_welcome_email and check_regional_ollama_health.
"""

from smtplib import SMTPException
from urllib.error import URLError

from celery import shared_task

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
