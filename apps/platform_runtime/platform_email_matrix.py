"""Platform Email Matrix — SOT for "what event sends what email to whom" (v4.00.98 Phase 2).

Every platform event that should generate an email gets a row in
:data:`EMAIL_MATRIX`. Each row carries:

* ``event_type``        — canonical event key (matches PlatformEventLog.event_type)
* ``classification``    — "operator" (RMC staff) | "tenant_admin" | "tenant_user"
                          | "marketing" | "system"
* ``subject_template``  — Django template string for the subject line
* ``body_template``     — path to a .txt template under templates/emails/
* ``html_template``     — optional path to .html template under templates/emails/
* ``recipient_resolver``— callable ``(payload) -> list[str]`` returning email addresses
* ``priority``          — "transactional" | "bulk" | "operator_alert"
* ``cooldown_minutes``  — minimum minutes between sends for the same (event_type, recipient)
                          key; 0 = no cooldown
* ``user_unsubscribable``— bool. False for legally-required operator alerts.

The dispatcher :func:`dispatch_email_for_event` is the single entrypoint.
It subscribes to :mod:`apps.platform_runtime.event_bus` so any
``publish_event(event_type, payload)`` automatically fans out to the
matrix.

Secret hygiene: payloads are scrubbed with the same denylist used by
:mod:`apps.platform_runtime.workflow_tracker._scrub` before render — secrets
never end up in the email body. Recipient resolvers may return ``[]``
to silently skip without raising.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Iterable

from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Classifications ────────────────────────────────────────────────────────
CLASSIFICATION_OPERATOR = "operator"          # → RMC platform staff
CLASSIFICATION_TENANT_ADMIN = "tenant_admin"  # → School admin / owner
CLASSIFICATION_TENANT_USER = "tenant_user"    # → Parent / teacher / student
CLASSIFICATION_MARKETING = "marketing"        # → Newsletter / promo (opt-in)
CLASSIFICATION_SYSTEM = "system"              # → Health probes / smoke

ALL_CLASSIFICATIONS: frozenset[str] = frozenset(
    {
        CLASSIFICATION_OPERATOR,
        CLASSIFICATION_TENANT_ADMIN,
        CLASSIFICATION_TENANT_USER,
        CLASSIFICATION_MARKETING,
        CLASSIFICATION_SYSTEM,
    }
)

# ── Priority levels ────────────────────────────────────────────────────────
PRIORITY_TRANSACTIONAL = "transactional"
PRIORITY_BULK = "bulk"
PRIORITY_OPERATOR_ALERT = "operator_alert"


@dataclass(frozen=True)
class EmailMatrixRow:
    """One entry in the platform email matrix."""

    event_type: str
    classification: str
    subject_template: str
    body_template: str
    recipient_resolver: Callable[[dict], list[str]]
    html_template: str = ""
    priority: str = PRIORITY_TRANSACTIONAL
    cooldown_minutes: int = 0
    user_unsubscribable: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if self.classification not in ALL_CLASSIFICATIONS:
            raise ValueError(
                f"EmailMatrixRow {self.event_type!r}: classification "
                f"{self.classification!r} not in {sorted(ALL_CLASSIFICATIONS)}"
            )
        if not callable(self.recipient_resolver):
            raise TypeError(
                f"EmailMatrixRow {self.event_type!r}: recipient_resolver must be callable"
            )


# ── Built-in recipient resolvers ───────────────────────────────────────────
def resolve_operator_inbox(payload: dict) -> list[str]:
    """Send to the operator alert inbox (env RMC_OPERATOR_ALERT_EMAIL),
    falling back to ADMINS in settings, falling back to the platform's
    DEFAULT_FROM_EMAIL so even with no config the message is debuggable."""

    from django.conf import settings

    target = (
        getattr(settings, "RMC_OPERATOR_ALERT_EMAIL", "")
        or getattr(settings, "OPERATOR_ALERT_EMAIL", "")
    )
    if target:
        return [str(target)]
    admins = list(getattr(settings, "ADMINS", []) or [])
    if admins:
        return [email for _, email in admins if email]
    fallback = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    return [str(fallback)] if fallback else []


def resolve_tenant_admin_from_payload(payload: dict) -> list[str]:
    """Pull the tenant admin email out of the event payload.

    Looks at common keys: ``admin_email``, ``tenant_admin_email``,
    ``owner_email``, then ``school_id`` → School.admins. Returns [] when
    nothing resolvable."""

    for key in ("admin_email", "tenant_admin_email", "owner_email"):
        value = payload.get(key)
        if value:
            return [str(value)]
    school_id = payload.get("school_id") or payload.get("school_pk")
    if not school_id:
        return []
    try:
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return []
        verification = getattr(school, "signupverification", None)
        if verification and getattr(verification, "email", ""):
            return [str(verification.email)]
        return []
    except Exception:
        logger.warning("email_matrix_tenant_admin_resolve_failed school_id=%s", school_id)
        return []


def resolve_from_payload_to_field(payload: dict) -> list[str]:
    """Generic resolver — uses payload['to'] (string or list)."""

    raw = payload.get("to") or payload.get("recipient") or payload.get("email")
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple, set)):
        return [str(x) for x in raw if x]
    return []


# ── In-process registry ────────────────────────────────────────────────────
# An event_type may fan out to MULTIPLE rows (e.g. tenant.payment.failed
# pings BOTH the operator inbox AND the tenant admin). Identity per slot is
# (event_type, classification) so re-registering the same pair is idempotent.
_REGISTRY: dict[tuple[str, str], EmailMatrixRow] = {}


def register_email_row(row: EmailMatrixRow) -> EmailMatrixRow:
    """Add or replace a matrix entry. Idempotent — same
    (event_type, classification) overwrites the existing row so
    AppConfig.ready re-runs are safe."""

    if not isinstance(row, EmailMatrixRow):
        raise TypeError("register_email_row requires an EmailMatrixRow")
    _REGISTRY[(row.event_type, row.classification)] = row
    return row


def get_email_row(event_type: str, classification: str | None = None) -> EmailMatrixRow | None:
    """Return the first row matching event_type (any classification when
    none supplied). For multi-row lookup use :func:`get_email_rows_for_event`.
    """
    if classification is not None:
        return _REGISTRY.get((event_type, classification))
    for key, row in _REGISTRY.items():
        if key[0] == event_type:
            return row
    return None


def get_email_rows_for_event(event_type: str) -> list[EmailMatrixRow]:
    return [row for (et, _cls), row in _REGISTRY.items() if et == event_type]


def all_email_rows() -> list[EmailMatrixRow]:
    return list(_REGISTRY.values())


def matrix_summary() -> dict:
    """Return a JSON-serializable summary of the matrix for the
    operator UI + CI gate. Counts per classification + priority + list
    of all (event_type, classification, priority) triples."""

    rows = all_email_rows()
    counts_by_class: dict[str, int] = {}
    counts_by_priority: dict[str, int] = {}
    for row in rows:
        counts_by_class[row.classification] = counts_by_class.get(row.classification, 0) + 1
        counts_by_priority[row.priority] = counts_by_priority.get(row.priority, 0) + 1
    return {
        "total": len(rows),
        "by_classification": counts_by_class,
        "by_priority": counts_by_priority,
        "rows": [
            {
                "event_type": r.event_type,
                "classification": r.classification,
                "priority": r.priority,
                "cooldown_minutes": r.cooldown_minutes,
                "user_unsubscribable": r.user_unsubscribable,
            }
            for r in rows
        ],
    }


# ── Dispatcher ─────────────────────────────────────────────────────────────
def _scrub_payload(payload: Any) -> dict:
    """Re-use the workflow_tracker scrubber (same 18-key denylist)."""

    try:
        from apps.platform_runtime.workflow_tracker import _scrub

        return _scrub(payload or {})
    except Exception:
        # Conservative fallback: drop dict, return empty
        if isinstance(payload, dict):
            return {k: v for k, v in payload.items() if "password" not in str(k).lower() and "token" not in str(k).lower()}
        return {}


def _cooldown_key(event_type: str, recipient: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{event_type}|{recipient.strip().lower()}".encode("utf-8")).hexdigest()
    return f"emxk:{digest[:24]}"


_COOLDOWN_RING: dict[str, float] = {}
_COOLDOWN_RING_CAP = 5000


def _in_cooldown(event_type: str, recipient: str, cooldown_minutes: int) -> bool:
    if cooldown_minutes <= 0:
        return False
    key = _cooldown_key(event_type, recipient)
    last = _COOLDOWN_RING.get(key)
    if last is None:
        return False
    age_seconds = timezone.now().timestamp() - last
    return age_seconds < (cooldown_minutes * 60)


def _record_cooldown(event_type: str, recipient: str) -> None:
    if len(_COOLDOWN_RING) >= _COOLDOWN_RING_CAP:
        # Drop oldest 10% to make room.
        for key in list(_COOLDOWN_RING.keys())[: _COOLDOWN_RING_CAP // 10]:
            _COOLDOWN_RING.pop(key, None)
    _COOLDOWN_RING[_cooldown_key(event_type, recipient)] = timezone.now().timestamp()


def _render_subject(template_string: str, payload: dict) -> str:
    try:
        return Template(template_string).render(Context(payload))
    except Exception:
        logger.warning("email_matrix_subject_render_failed event=%s", payload.get("_event_type"))
        return template_string[:120]


def _render_body(template_path: str, payload: dict) -> str:
    try:
        return render_to_string(template_path, payload)
    except Exception as exc:
        logger.warning(
            "email_matrix_body_render_failed template=%s err=%s",
            template_path,
            type(exc).__name__,
        )
        return ""


def dispatch_email_for_event(
    event_type: str,
    payload: dict | None = None,
    *,
    tenant_hash: str | None = None,
    idempotency_key: str = "",
) -> dict:
    """Look up every row registered for ``event_type`` and fire
    send_transactional for each resolved recipient on each row.

    A single event_type can fan out to multiple rows (e.g. payment.failed
    sends to BOTH operator inbox AND the tenant admin). Each row resolves
    its own recipients + renders its own subject/body.

    Returns a dict with per-row per-recipient send results. NEVER raises —
    every failure is logged + returned in the envelope. Safe to call from
    any request path or Celery task."""

    rows = get_email_rows_for_event(event_type)
    if not rows:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_matrix_row",
            "event_type": event_type,
            "row_results": [],
        }

    row_results = []
    for row in rows:
        row_results.append(
            _dispatch_one_row(
                row,
                payload or {},
                tenant_hash=tenant_hash,
                idempotency_key=idempotency_key,
            )
        )
    overall_ok = all(r.get("ok", False) for r in row_results)
    return {
        "ok": overall_ok,
        "skipped": False,
        "event_type": event_type,
        "row_count": len(row_results),
        "row_results": row_results,
        # Convenience: the first non-skipped row's classification + count
        # for tests/UI that only care about the operator branch.
        "classification": next(
            (r["classification"] for r in row_results if r.get("recipient_count")),
            (row_results[0].get("classification") if row_results else None),
        ),
        "recipient_count": sum(r.get("recipient_count", 0) for r in row_results),
        "skipped_cooldown_count": sum(r.get("skipped_cooldown_count", 0) for r in row_results),
        "skipped_unsubscribed_count": sum(r.get("skipped_unsubscribed_count", 0) for r in row_results),
        "results": [item for r in row_results for item in (r.get("results") or [])],
    }


def _dispatch_one_row(
    row: EmailMatrixRow,
    payload: dict,
    *,
    tenant_hash: str | None = None,
    idempotency_key: str = "",
) -> dict:
    event_type = row.event_type
    scrubbed = _scrub_payload(payload or {})
    scrubbed["_event_type"] = event_type
    scrubbed.setdefault("generated_at", timezone.now().isoformat())

    try:
        recipients = row.recipient_resolver(scrubbed) or []
    except Exception as exc:
        logger.exception("email_matrix_resolver_failed event=%s", event_type)
        return {
            "ok": False,
            "skipped": False,
            "reason": f"resolver_error:{type(exc).__name__}",
            "event_type": event_type,
            "results": [],
        }

    if not recipients:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_recipients",
            "event_type": event_type,
            "results": [],
        }

    subject = _render_subject(row.subject_template, scrubbed)
    body = _render_body(row.body_template, scrubbed)
    html_body = _render_body(row.html_template, scrubbed) if row.html_template else ""

    # Apply unsubscribe + suppression checks for non-operator classifications.
    visible_recipients: list[str] = []
    skipped_unsubscribed: list[str] = []
    for recipient in recipients:
        if row.classification != CLASSIFICATION_OPERATOR and is_unsubscribed(recipient, row.classification):
            skipped_unsubscribed.append(recipient)
            continue
        visible_recipients.append(recipient)

    # Apply cooldown.
    after_cooldown: list[str] = []
    skipped_cooldown: list[str] = []
    for recipient in visible_recipients:
        if _in_cooldown(event_type, recipient, row.cooldown_minutes):
            skipped_cooldown.append(recipient)
            continue
        after_cooldown.append(recipient)

    try:
        from apps.schoolops.email_delivery import send_transactional
    except Exception:
        return {
            "ok": False,
            "reason": "reliability_layer_unavailable",
            "event_type": event_type,
            "results": [],
        }

    results = []
    for recipient in after_cooldown:
        try:
            result = send_transactional(
                subject=subject,
                body=body or subject,
                to=recipient,
                html_body=html_body or None,
                priority=row.priority if row.priority in ("transactional", "bulk") else "transactional",
                tenant_hash=tenant_hash,
                idempotency_key=(idempotency_key or "") + f":{event_type}:{recipient[:32]}",
                headers={"X-RMC-Event-Type": event_type, "X-RMC-Classification": row.classification},
            )
            results.append({"recipient_hash": _hash_for_log(recipient), "result": result})
            if result.get("ok"):
                _record_cooldown(event_type, recipient)
        except Exception as exc:
            logger.exception("email_matrix_send_failed event=%s", event_type)
            results.append(
                {
                    "recipient_hash": _hash_for_log(recipient),
                    "result": {"ok": False, "error_kind": f"exception:{type(exc).__name__}"},
                }
            )

    return {
        "ok": all(r["result"].get("ok") for r in results) if results else True,
        "skipped": False,
        "event_type": event_type,
        "classification": row.classification,
        "recipient_count": len(after_cooldown),
        "skipped_unsubscribed_count": len(skipped_unsubscribed),
        "skipped_cooldown_count": len(skipped_cooldown),
        "results": results,
    }


def _hash_for_log(recipient: str) -> str:
    import hashlib

    return hashlib.sha256(recipient.lower().encode("utf-8")).hexdigest()[:12]


# ── Unsubscribe registry (in-process + DB-backed via Phase 3 model) ───────
def is_unsubscribed(recipient: str, classification: str) -> bool:
    """Check whether ``recipient`` has unsubscribed from ``classification``.

    Operator and system classifications are NEVER subject to unsubscribe
    (legally + operationally required). Tenant / marketing classifications
    consult the NewsletterSubscription model (Phase 3) when present.
    """

    if classification in (CLASSIFICATION_OPERATOR, CLASSIFICATION_SYSTEM):
        return False
    try:
        from apps.platform_runtime.models import NewsletterSubscription

        row = NewsletterSubscription.objects.filter(email__iexact=recipient).first()
        if row is None:
            return False
        if classification == CLASSIFICATION_MARKETING:
            return bool(row.unsubscribed_at)
        # Tenant emails are NOT blocked by newsletter unsub; they are
        # transactional. Only marketing class is gated.
        return False
    except Exception:
        # Phase 3 model may not yet be migrated in a fresh tree.
        return False


# ── Event bus integration ──────────────────────────────────────────────────
def register_email_matrix_event_subscriber() -> None:
    """Subscribe to platform_runtime.event_bus so every published event
    that matches a matrix row triggers an email dispatch."""

    try:
        from apps.platform_runtime.event_bus import register_subscriber

        def _handle(payload, *, event_type, tenant_id=None, school_id=None, event_id=None, **_kwargs):
            try:
                merged = dict(payload or {})
                if school_id and "school_id" not in merged:
                    merged["school_id"] = school_id
                if tenant_id and "tenant_id" not in merged:
                    merged["tenant_id"] = tenant_id
                # Use the platform event's primary key as the idempotency
                # seed so each published event fires a fresh email even when
                # the (event_type, recipient) pair has been used in a prior
                # event row.
                idem = f"plat_evt_{event_id}" if event_id else ""
                dispatch_email_for_event(event_type, merged, idempotency_key=idem)
            except Exception:
                logger.exception("email_matrix_event_subscriber_failed event=%s", event_type)

        register_subscriber("*", _handle)
    except Exception:
        logger.debug("email_matrix_event_subscriber_registration_failed", exc_info=True)
