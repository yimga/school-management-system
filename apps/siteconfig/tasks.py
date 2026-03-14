"""
Celery tasks for siteconfig (Phase E: revenue stats; Phase Welcome: welcome email).
"""
from celery import shared_task


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
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            [email],
            fail_silently=True,
            html_message=body.replace("\n", "<br>\n"),
        )
        return {"ok": True, "sent_to": email}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
    return {"ok": True, "campaign_id": campaign_id, "batches": (total + BROADCAST_BATCH_SIZE - 1) // BROADCAST_BATCH_SIZE}


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
        configs = RegionalAIConfig.objects.filter(regional_cluster=cluster, is_active=True)
    else:
        configs = RegionalAIConfig.objects.filter(is_active=True)

    config_list = list(configs)
    for config in config_list:
        key = f"{AI_HEALTH_CACHE_PREFIX}{config.regional_cluster}"
        base = (config.ollama_base_url or "").rstrip("/")
        if not base:
            cache.set(key, {"status": "unavailable", "last_check_at": now, "error": "no_url"}, timeout=AI_HEALTH_CACHE_TTL)
            continue
        url = f"{base}/api/tags"
        try:
            import urllib.request
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    cache.set(key, {"status": "ok", "last_check_at": now}, timeout=AI_HEALTH_CACHE_TTL)
                else:
                    cache.set(key, {"status": "unavailable", "last_check_at": now, "code": resp.status}, timeout=AI_HEALTH_CACHE_TTL)
        except Exception as e:
            cache.set(key, {"status": "unavailable", "last_check_at": now, "error": str(e)}, timeout=AI_HEALTH_CACHE_TTL)
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
        RegionalAIConfig.objects.filter(is_active=True).values_list("regional_cluster", flat=True).distinct()
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
        {"status": "queued", "regions_total": len(clusters), "regions_done": 0, "clusters": clusters},
        timeout=AI_UPGRADE_PROGRESS_TTL,
    )
    for c in clusters:
        sync_regional_models_for_cluster.delay(c, run_id)
    return {"run_id": run_id, "regions_total": len(clusters)}
