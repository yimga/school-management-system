"""
Runtime constants — magic numbers extracted from app code so they can be tuned
per-environment without code edits.

Read these via Django settings (each name is mirrored into `settings.py`) or
import directly from this module. Anything in here MUST be safe to change at
deploy time without code changes.

See `docs/CONFIGURABILITY.md` (Layer B) for the contract.
"""
import os


def _env_int(name: str, default: int) -> int:
    """Read an int env var with fallback. Never raises — falls back on bad input."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# HTTP outbound (third-party API calls)
# ---------------------------------------------------------------------------
# Short = health checks, dependency probes, low-stakes lookups.
# Standard = normal external API calls (Clever, ClassLink, SMS, email).
# Long = batch / OCR / file conversion (LibreOffice, receipt OCR).
HTTP_OUTBOUND_TIMEOUT_SHORT = _env_int("HTTP_OUTBOUND_TIMEOUT_SHORT", 5)
HTTP_OUTBOUND_TIMEOUT_STANDARD = _env_int("HTTP_OUTBOUND_TIMEOUT_STANDARD", 15)
HTTP_OUTBOUND_TIMEOUT_LONG = _env_int("HTTP_OUTBOUND_TIMEOUT_LONG", 30)
HTTP_OUTBOUND_TIMEOUT_BATCH = _env_int("HTTP_OUTBOUND_TIMEOUT_BATCH", 90)

# ---------------------------------------------------------------------------
# Celery task defaults
# ---------------------------------------------------------------------------
DEFAULT_TASK_MAX_RETRIES = _env_int("DEFAULT_TASK_MAX_RETRIES", 3)
DEFAULT_TASK_RETRY_BACKOFF_SECONDS = _env_int("DEFAULT_TASK_RETRY_BACKOFF_SECONDS", 60)
# A few task families want a smaller retry budget (welcome email; one shot ok to drop)
WELCOME_EMAIL_MAX_RETRIES = _env_int("WELCOME_EMAIL_MAX_RETRIES", 2)
# Offline sync replay tolerates more retries since network is the usual fault
OFFLINE_SYNC_MAX_RETRIES = _env_int("OFFLINE_SYNC_MAX_RETRIES", 5)

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_SHORT = _env_int("CACHE_TTL_SHORT", 60)            # 1 min
CACHE_TTL_MEDIUM = _env_int("CACHE_TTL_MEDIUM", 300)         # 5 min
CACHE_TTL_LONG = _env_int("CACHE_TTL_LONG", 3600)            # 1 hour
CACHE_TTL_DAY = _env_int("CACHE_TTL_DAY", 86400)             # 24 hours
CACHE_TTL_WEEK = _env_int("CACHE_TTL_WEEK", 86400 * 7)       # 1 week
CACHE_TTL_MONTH = _env_int("CACHE_TTL_MONTH", 86400 * 30)    # 30 days
CACHE_TTL_QUARTER = _env_int("CACHE_TTL_QUARTER", 86400 * 90)  # 90 days
CACHE_TTL_YEAR = _env_int("CACHE_TTL_YEAR", 86400 * 365)     # 365 days

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
# Django admin (high-density operator views) — bigger than user-facing pagination
DEFAULT_ADMIN_PAGE_SIZE = _env_int("DEFAULT_ADMIN_PAGE_SIZE", 50)
# Compliance / audit lists that benefit from deeper paging
DEFAULT_AUDIT_PAGE_SIZE = _env_int("DEFAULT_AUDIT_PAGE_SIZE", 100)
# Standard user-facing pagination (portal, parent, teacher views)
DEFAULT_PAGE_SIZE = _env_int("DEFAULT_PAGE_SIZE", 25)
# Compact widgets (recent activity, glance lists)
DEFAULT_WIDGET_PAGE_SIZE = _env_int("DEFAULT_WIDGET_PAGE_SIZE", 10)

# ---------------------------------------------------------------------------
# Upload limits (bytes)
# ---------------------------------------------------------------------------
MAX_PHOTO_UPLOAD_BYTES = _env_int("MAX_PHOTO_UPLOAD_BYTES", 10 * 1024 * 1024)  # 10 MB
MAX_DOCUMENT_UPLOAD_BYTES = _env_int(
    "MAX_DOCUMENT_UPLOAD_BYTES", 20 * 1024 * 1024
)  # 20 MB
MAX_CSV_IMPORT_BYTES = _env_int("MAX_CSV_IMPORT_BYTES", 5 * 1024 * 1024)  # 5 MB

# ---------------------------------------------------------------------------
# Report card grade weighting (assessment percentages summing to 100)
# Cameroon-default: sequence 1 (20%) + sequence 2 (20%) + exam (60%) + mock (0%) + practical (0%).
# UK / 3-term defaults differ. Override per environment via env vars below, or
# per-tenant via SiteSettings.report_grade_weights JSON at view-time.
# Used as the FALLBACK in preview / unconfigured paths.
# ---------------------------------------------------------------------------
GRADE_WEIGHT_SEQ1 = _env_int("GRADE_WEIGHT_SEQ1", 20)
GRADE_WEIGHT_SEQ2 = _env_int("GRADE_WEIGHT_SEQ2", 20)
GRADE_WEIGHT_EXAM = _env_int("GRADE_WEIGHT_EXAM", 60)
GRADE_WEIGHT_MOCK = _env_int("GRADE_WEIGHT_MOCK", 0)
GRADE_WEIGHT_PRACTICAL = _env_int("GRADE_WEIGHT_PRACTICAL", 0)


def default_grade_weights() -> dict[str, int]:
    """Return the platform-default grade weight dict.

    Callers should prefer tenant-specific weights from SiteSettings /
    EvalsConfig if available and fall back to this helper.
    """
    return {
        "seq1": GRADE_WEIGHT_SEQ1,
        "seq2": GRADE_WEIGHT_SEQ2,
        "exam": GRADE_WEIGHT_EXAM,
        "mock": GRADE_WEIGHT_MOCK,
        "practical": GRADE_WEIGHT_PRACTICAL,
    }
