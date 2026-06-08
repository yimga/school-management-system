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

    def _validate_key_namespace(self, entity: str, op: Any) -> None:
        key = (
            getattr(op, "key", None)
            or getattr(op, "set_key", None)
            or getattr(op, "counter_key", None)
            or ""
        )
        if not str(key).startswith(f"{entity}:"):
            raise ValueError(f"crdt_key_must_start_with:{entity}:")

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
