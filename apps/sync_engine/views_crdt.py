"""v4.00.13 — CRDT ops POST view.

Closes the v4.00.12 follow-on gap: the CRDT wire protocol existed but no
Django view applied submitted ops to per-tenant state. This view accepts a
JSON body of ops, parses each via ``parse_wire_op``, merges into the
per-tenant state at ``school.settings["crdt_state"]``, and returns the
materialized view to the client.

Idempotent — same op list applied twice converges to the same state. The
per-tenant state has 3 sections matching the protocol kinds:

    school.settings["crdt_state"] = {
        "lww":    {key: {value, hlc}},       # last-write-wins registers
        "orset":  {set_key: {element: [tags]}},   # observed-remove sets
        "gcounter": {counter_key: {actor_id: int}},  # grow-only counters
    }

The view does NOT enforce a particular wire schema for higher-level
entity types — that's the caller's contract. This is the merge engine.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.views import View

logger = logging.getLogger(__name__)


@method_decorator([login_required, csrf_protect], name="dispatch")
class CRDTOpsApplyView(View):
    """POST /api/v1/crdt/apply/  body: {"ops": [<op>, ...]}.

    # rbac-allow: authenticated-user-crdt-apply
    """

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
            return JsonResponse({"error": "too_many_ops", "limit": self.max_ops_per_request}, status=400)

        tenant = getattr(request, "tenant", None) or getattr(request, "school", None)
        if tenant is None or getattr(tenant, "pk", None) is None:
            return JsonResponse({"error": "no_tenant"}, status=400)

        from apps.sync_engine.crdt_wire_protocol import (
            GCounterOp,
            LWWOp,
            ORSetOp,
            gcounter_merge,
            gcounter_value,
            lww_merge,
            orset_materialize,
            orset_merge,
            parse_wire_op,
        )

        state = self._read_state(tenant)
        applied = 0
        rejected: list[dict[str, Any]] = []

        for index, raw in enumerate(ops_raw):
            try:
                op = parse_wire_op(raw)
            except ValueError as exc:
                rejected.append({"index": index, "reason": str(exc)})
                continue
            try:
                if isinstance(op, LWWOp):
                    current = state["lww"].get(op.key)
                    if current is None:
                        winner = op
                    else:
                        winner = lww_merge(
                            self._deserialize_lww(current, op.key), op,
                        )
                    state["lww"][op.key] = {"value": winner.value, "hlc": winner.hlc.to_wire()}
                elif isinstance(op, ORSetOp):
                    set_state_raw = state["orset"].get(op.set_key) or {}
                    set_state = {k: set(v) for k, v in set_state_raw.items() if isinstance(v, list)}
                    new_set_state = orset_merge(set_state, op)
                    state["orset"][op.set_key] = {k: sorted(v) for k, v in new_set_state.items()}
                elif isinstance(op, GCounterOp):
                    counter_state = dict(state["gcounter"].get(op.counter_key) or {})
                    new_counter = gcounter_merge(counter_state, op)
                    state["gcounter"][op.counter_key] = new_counter
                applied += 1
            except ValueError as exc:
                rejected.append({"index": index, "reason": str(exc)})
                continue

        self._write_state(tenant, state)

        # Build a compact materialized view so clients can sync UI immediately.
        materialized = {
            "lww":      {k: v["value"] for k, v in state["lww"].items()},
            "orset":    {k: sorted(orset_materialize({e: set(tags) for e, tags in v.items()}))
                         for k, v in state["orset"].items()},
            "gcounter": {k: gcounter_value(v) for k, v in state["gcounter"].items()},
        }
        return JsonResponse({
            "applied": applied,
            "rejected": rejected,
            "materialized": materialized,
        })

    def _deserialize_lww(self, current: dict[str, Any], key: str):
        from apps.sync_engine.crdt_wire_protocol import HLC, LWWOp

        return LWWOp(
            kind="LWW", key=key, value=current.get("value"),
            hlc=HLC.from_wire(str(current.get("hlc") or "0:0:")),
        )

    def _read_state(self, tenant: Any) -> dict[str, dict[str, Any]]:
        settings = getattr(tenant, "settings", None) or {}
        if not isinstance(settings, dict):
            settings = {}
        crdt = settings.get("crdt_state") or {}
        if not isinstance(crdt, dict):
            crdt = {}
        return {
            "lww":      dict(crdt.get("lww") or {}),
            "orset":    dict(crdt.get("orset") or {}),
            "gcounter": dict(crdt.get("gcounter") or {}),
        }

    def _write_state(self, tenant: Any, state: dict[str, dict[str, Any]]) -> None:
        try:
            settings = getattr(tenant, "settings", None) or {}
            if not isinstance(settings, dict):
                settings = {}
            settings["crdt_state"] = state
            tenant.settings = settings
            tenant.save(update_fields=["settings"])
        except Exception as exc:  # noqa: BLE001 — never break the request
            logger.warning("crdt apply: persist failed: %s", exc)
