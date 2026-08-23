"""Governed CRDT operation endpoint for approved low-risk sync namespaces."""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

#: Ceilings on what one tenant may accumulate here. The rail is documented as
#: "sized for the small, approved namespaces ... not a general document store"
#: (docs/CRDT_LIVE_RAIL.md), and the state lands in ``School.settings`` -- a
#: JSONField on the row the tenant middleware loads on EVERY request to that
#: school. Nothing anywhere reads ``crdt_state`` back, so there is no eviction
#: either: without a ceiling the only bound on it is how long someone keeps
#: POSTing, and the cost is paid by every page load for the whole school.
_DEFAULT_MAX_KEY_CHARS = 128  # magic-number-allow: CRDT key length ceiling (chars)
_DEFAULT_MAX_VALUE_BYTES = 4096  # magic-number-allow: CRDT op value ceiling (bytes)
_DEFAULT_MAX_STATE_BYTES = 262144  # magic-number-allow: CRDT tenant state ceiling (bytes)


def _max_key_chars() -> int:
    from django.conf import settings as dj_settings

    return max(1, int(getattr(dj_settings, "RMC_CRDT_MAX_KEY_CHARS", _DEFAULT_MAX_KEY_CHARS)))


def _max_value_bytes() -> int:
    from django.conf import settings as dj_settings

    return max(1, int(getattr(dj_settings, "RMC_CRDT_MAX_VALUE_BYTES", _DEFAULT_MAX_VALUE_BYTES)))


def _max_state_bytes() -> int:
    from django.conf import settings as dj_settings

    return max(1, int(getattr(dj_settings, "RMC_CRDT_MAX_STATE_BYTES", _DEFAULT_MAX_STATE_BYTES)))


@method_decorator([login_required, csrf_protect], name="dispatch")
class CRDTOpsApplyView(View):
    """POST approved CRDT operations into tenant-bound state."""

    max_ops_per_request = 200

    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid_json"}, status=400)

        ops_raw = payload.get("ops")
        if not isinstance(ops_raw, list):
            return JsonResponse({"error": "ops_must_be_list"}, status=400)
        if len(ops_raw) > self.max_ops_per_request:
            return JsonResponse(
                {"error": "too_many_ops", "limit": self.max_ops_per_request},
                status=400,
            )

        tenant = getattr(request, "tenant", None) or getattr(request, "school", None)
        if tenant is None or getattr(tenant, "pk", None) is None:
            return JsonResponse({"error": "no_tenant"}, status=400)

        if not self._has_standing(request.user, tenant):
            return JsonResponse({"error": "no_standing_in_tenant"}, status=403)

        from apps.sync_engine.crdt_wire_protocol import (
            GCounterOp,
            HLC,
            LWWOp,
            ORSetOp,
            gcounter_merge,
            gcounter_value,
            lww_merge,
            orset_materialize,
            orset_merge,
            parse_wire_op,
        )
        from apps.sync_engine.policy_registry import POLICY_VERSION, validate_crdt_kind

        applied = 0
        rejected: list[dict[str, Any]] = []
        actor_id = self._bound_actor_id(request, payload)

        with transaction.atomic():
            locked_tenant = (
                type(tenant)._default_manager.select_for_update().get(pk=tenant.pk)
            )
            state = self._read_state(locked_tenant)
            for index, raw in enumerate(ops_raw):
                try:
                    if not isinstance(raw, dict):
                        raise ValueError("op must be a dict")
                    entity = str(raw.get("entity") or "").strip().lower()
                    validate_crdt_kind(entity, raw.get("kind"))
                    op = parse_wire_op(raw)
                    self._validate_key_namespace(entity, op)
                    self._validate_op_size(op)

                    if isinstance(op, LWWOp):
                        bound_op = LWWOp(
                            kind=op.kind,
                            key=op.key,
                            value=op.value,
                            hlc=HLC(
                                physical_ms=op.hlc.physical_ms,
                                logical=op.hlc.logical,
                                actor_id=actor_id,
                            ),
                        )
                        current = state["lww"].get(bound_op.key)
                        winner = (
                            bound_op
                            if current is None
                            else lww_merge(
                                self._deserialize_lww(current, bound_op.key),
                                bound_op,
                            )
                        )
                        state["lww"][bound_op.key] = {
                            "value": winner.value,
                            "hlc": winner.hlc.to_wire(),
                        }
                    elif isinstance(op, ORSetOp):
                        raw_set = state["orset"].get(op.set_key) or {}
                        set_state = {
                            key: set(tags)
                            for key, tags in raw_set.items()
                            if isinstance(tags, list)
                        }
                        merged = orset_merge(set_state, op)
                        state["orset"][op.set_key] = {
                            key: sorted(tags) for key, tags in merged.items()
                        }
                    elif isinstance(op, GCounterOp):
                        bound_op = GCounterOp(
                            kind=op.kind,
                            counter_key=op.counter_key,
                            actor_id=actor_id,
                            value=op.value,
                        )
                        counter_state = dict(
                            state["gcounter"].get(bound_op.counter_key) or {}
                        )
                        state["gcounter"][bound_op.counter_key] = gcounter_merge(
                            counter_state, bound_op
                        )
                    applied += 1
                except (KeyError, TypeError, ValueError) as exc:
                    rejected.append({"index": index, "reason": str(exc)})

            state["policy_version"] = POLICY_VERSION
            # Individually-legal ops still add up. The ceiling is checked on the
            # ACCUMULATED state, immediately before it is persisted, because that is
            # the thing every later request to this school pays to load.
            over_by = self._state_overflow(state)
            if over_by > 0:
                transaction.set_rollback(True)
                return JsonResponse(
                    {
                        "error": "crdt_state_full",
                        "limit_bytes": _max_state_bytes(),
                        "over_by_bytes": over_by,
                    },
                    status=413,
                )
            self._write_state(locked_tenant, state)

        materialized = {
            "lww": {
                key: value["value"] for key, value in state["lww"].items()
            },
            "orset": {
                key: sorted(
                    orset_materialize(
                        {element: set(tags) for element, tags in value.items()}
                    )
                )
                for key, value in state["orset"].items()
            },
            "gcounter": {
                key: gcounter_value(value)
                for key, value in state["gcounter"].items()
            },
        }
        return JsonResponse(
            {
                "applied": applied,
                "rejected": rejected,
                "materialized": materialized,
                "policy_version": POLICY_VERSION,
            }
        )

    def _bound_actor_id(
        self, request: HttpRequest, payload: dict[str, Any]
    ) -> str:
        device_id = str(payload.get("device_id") or "browser").strip()[:64]
        safe_device = "".join(
            char for char in device_id if char.isalnum() or char in "._-"
        ) or "browser"
        return f"u{request.user.pk}:{safe_device}"

    def _has_standing(self, user, tenant) -> bool:
        """May ``user`` write into THIS school's converged state?

        ``login_required`` alone answered "is anyone signed in", never "does this
        person belong to the school whose settings row is about to be rewritten" --
        and the tenant comes from the request, not from the user. The check is a
        LIVE, non-suspended membership: the same standing test
        ``pairing_service.may_adopt_for`` settled on, for the reason recorded there
        (the role-shaped checks are not school-scoped, so as an ``or`` they re-open
        exactly the hole this closes). Platform staff pass by design.
        """
        from apps.sync_engine.pairing_service import is_platform_staff

        if is_platform_staff(user):
            return True
        if not getattr(user, "is_authenticated", False):
            return False
        try:
            from apps.schools.models import SchoolMembership

            # tenant-isolation-allow: standing-check-is-explicitly-scoped-to-the-bound-school
            return SchoolMembership.objects.filter(
                school=tenant,
                user_id=getattr(user, "pk", None),
                suspended_at__isnull=True,
            ).exists()
        except (AttributeError, ImportError, TypeError, ValueError):
            return False

    def _key_of(self, op: Any) -> str:
        return str(
            getattr(op, "key", None)
            or getattr(op, "set_key", None)
            or getattr(op, "counter_key", None)
            or ""
        )

    def _validate_key_namespace(self, entity: str, op: Any) -> None:
        if not self._key_of(op).startswith(f"{entity}:"):
            raise ValueError(f"crdt_key_must_start_with:{entity}:")

    def _validate_op_size(self, op: Any) -> None:
        """Per-op ceilings.

        ``parse_wire_op`` applies none of its own -- ``key`` is any string and
        ``value`` is arbitrary JSON -- so this is where a padded key or a fat value
        is refused, before it can reach the accumulated state.
        """
        key = self._key_of(op)
        if len(key) > _max_key_chars():
            raise ValueError(f"crdt_key_too_long:{_max_key_chars()}")
        element = getattr(op, "element", None)
        if element is not None and len(str(element)) > _max_key_chars():
            raise ValueError(f"crdt_element_too_long:{_max_key_chars()}")
        if hasattr(op, "value") and not isinstance(op.value, int):
            try:
                encoded = json.dumps(op.value, default=str).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"crdt_value_not_serializable:{exc}") from exc
            if len(encoded) > _max_value_bytes():
                raise ValueError(f"crdt_value_too_large:{_max_value_bytes()}")

    def _state_overflow(self, state: dict[str, Any]) -> int:
        """Bytes by which ``state`` exceeds the per-tenant ceiling, or 0."""
        try:
            size = len(json.dumps(state, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            return 0
        return max(0, size - _max_state_bytes())

    def _deserialize_lww(self, current: dict[str, Any], key: str):
        from apps.sync_engine.crdt_wire_protocol import HLC, LWWOp

        return LWWOp(
            kind="LWW",
            key=key,
            value=current.get("value"),
            hlc=HLC.from_wire(str(current.get("hlc") or "0:0:legacy")),
        )

    def _read_state(self, tenant: Any) -> dict[str, Any]:
        settings = getattr(tenant, "settings", None) or {}
        if not isinstance(settings, dict):
            settings = {}
        crdt = settings.get("crdt_state") or {}
        if not isinstance(crdt, dict):
            crdt = {}
        return {
            "lww": dict(crdt.get("lww") or {}),
            "orset": dict(crdt.get("orset") or {}),
            "gcounter": dict(crdt.get("gcounter") or {}),
            "policy_version": int(crdt.get("policy_version") or 0),
        }

    def _write_state(self, tenant: Any, state: dict[str, Any]) -> None:
        settings = getattr(tenant, "settings", None) or {}
        if not isinstance(settings, dict):
            settings = {}
        settings["crdt_state"] = state
        tenant.settings = settings
        tenant.save(update_fields=["settings"])
