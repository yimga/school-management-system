"""
Evaluate backlog items against verifiable criteria (scripts, external/program tags).

Registry: backlog_unlock_registry.json (extend when new gates ship).
See docs/BACKLOG_UNLOCK_AUTOMATION.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.utils.dateparse import parse_datetime

REGISTRY_FILENAME = "backlog_unlock_registry.json"

PROFILE_SMOKE = "smoke"
PROFILE_FULL = "full"
_VALID_PROFILES = frozenset({PROFILE_SMOKE, PROFILE_FULL})


def normalize_profile(name: str | None) -> str:
    n = (name or PROFILE_FULL).strip().lower()
    return n if n in _VALID_PROFILES else PROFILE_FULL


def item_profiles(raw_item: dict[str, Any]) -> list[str]:
    p = raw_item.get("profiles")
    if p is None:
        return [PROFILE_FULL]
    if isinstance(p, str):
        p = [p]
    out = [str(x).strip().lower() for x in p if str(x).strip()]
    return out if out else [PROFILE_FULL]


def item_in_profile(raw_item: dict[str, Any], profile: str) -> bool:
    return normalize_profile(profile) in item_profiles(raw_item)


def snapshot_cache_key(profile: str) -> str:
    """Django cache key for evaluate JSON snapshot (per profile)."""
    return f"backlog_unlock:eval:{normalize_profile(profile)}:v1"


def states_cache_key(profile: str) -> str:
    """Django cache key for last item display_status map (transition detection)."""
    return f"backlog_unlock:states:{normalize_profile(profile)}:v1"


def aging_cache_key(profile: str) -> str:
    """Django cache key for first-seen timestamps in waiting / ready_attention columns."""
    return f"backlog_unlock:aging:{normalize_profile(profile)}:v1"


def registry_path() -> Path:
    return Path(__file__).resolve().parent / REGISTRY_FILENAME


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"registry_version": 0, "items": []}
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def _run_script(
    repo_root: Path,
    script_relative: str,
    args: list[str],
    timeout: int,
) -> tuple[bool, str]:
    script_path = repo_root / script_relative
    if not script_path.is_file():
        return False, f"Missing script: {script_relative}"
    cmd = [sys.executable, str(script_path), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s): {' '.join(cmd)}"
    except OSError as e:
        return False, f"Could not run script: {e}"
    tail = ""
    if proc.stdout:
        tail = proc.stdout[-2000:]
    if proc.stderr and proc.returncode != 0:
        tail = (proc.stderr[-2000:] + "\n" + tail)[-4000:]
    ok = proc.returncode == 0
    detail = "exit 0" if ok else f"exit {proc.returncode}"
    if not ok and tail.strip():
        detail = f"{detail}\n---\n{tail.strip()}"
    return ok, detail


def _run_pytest(
    repo_root: Path,
    targets: list[str],
    extra_args: list[str],
    timeout: int,
) -> tuple[bool, str]:
    if not targets:
        return False, "pytest_exit_zero: no targets"
    cmd = [sys.executable, "-m", "pytest", *targets, *extra_args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=max(1, timeout),
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s): {' '.join(cmd)}"
    except OSError as e:
        return False, f"Could not run pytest: {e}"
    tail = ""
    if proc.stdout:
        tail = proc.stdout[-2500:]
    if proc.stderr and proc.returncode != 0:
        tail = (proc.stderr[-2500:] + "\n" + tail)[-5000:]
    ok = proc.returncode == 0
    detail = "exit 0" if ok else f"exit {proc.returncode}"
    if not ok and tail.strip():
        detail = f"{detail}\n---\n{tail.strip()}"
    return ok, detail


def _automated_results(criterion_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        c
        for c in criterion_results
        if c.get("type") in ("script_exit_zero", "pytest_exit_zero")
    ]


def evaluate_criterion(
    repo_root: Path,
    spec: dict[str, Any],
    default_timeout: int,
) -> dict[str, Any]:
    ctype = spec.get("type", "")
    if ctype == "script_exit_zero":
        script = str(spec.get("script", "")).strip()
        args = list(spec.get("args") or [])
        timeout = int(spec.get("timeout_seconds", default_timeout))
        ok, detail = _run_script(repo_root, script, args, timeout)
        return {
            "type": ctype,
            "script": script,
            "ok": ok,
            "detail": detail,
        }
    if ctype == "pytest_exit_zero":
        raw_targets = spec.get("targets") or []
        if isinstance(raw_targets, str):
            raw_targets = [raw_targets]
        targets = [str(t).strip() for t in raw_targets if str(t).strip()]
        extra = list(spec.get("args") or ["-q", "--no-header"])
        timeout = int(spec.get("timeout_seconds", default_timeout))
        ok, detail = _run_pytest(repo_root, targets, extra, timeout)
        return {
            "type": ctype,
            "targets": targets,
            "ok": ok,
            "detail": detail,
        }
    return {
        "type": ctype or "unknown",
        "ok": False,
        "detail": f"Unsupported criterion type: {ctype!r}",
    }


def _item_display_status(
    kind: str,
    criterion_results: list[dict[str, Any]],
) -> str:
    if kind == "external_blocker":
        return "blocked_external"
    script_results = _automated_results(criterion_results)
    if kind == "program_partial":
        if not script_results:
            return "ready_attention"
        if all(c.get("ok") for c in script_results):
            return "ready_attention"
        return "waiting"
    if not script_results:
        return "waiting"
    if all(c.get("ok") for c in script_results):
        return "ready"
    return "waiting"


def evaluate_all(
    repo_root: Path | None = None,
    *,
    profile: str = PROFILE_FULL,
    default_script_timeout: int = 420,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parent.parent.parent
    prof = normalize_profile(profile)
    data = load_registry()
    all_raw = [x for x in data.get("items", []) if isinstance(x, dict)]
    selected_raw = [x for x in all_raw if item_in_profile(x, prof)]
    items_out: list[dict[str, Any]] = []
    for raw in selected_raw:
        iid = str(raw.get("id", ""))
        title = str(raw.get("title", iid))
        category = str(raw.get("category", "general"))
        kind = str(raw.get("kind", "verification"))
        doc_href = str(raw.get("doc_href", ""))
        action_hint = str(raw.get("action_hint", ""))
        sot_refs = list(raw.get("sot_refs") or [])
        max_days_in_waiting = raw.get("max_days_in_waiting")
        max_days_in_ready_attention = raw.get("max_days_in_ready_attention")
        criterion_results: list[dict[str, Any]] = []
        if kind == "external_blocker":
            pass
        else:
            for crit in raw.get("criteria") or []:
                if isinstance(crit, dict):
                    criterion_results.append(
                        evaluate_criterion(root, crit, default_script_timeout)
                    )
        display = _item_display_status(kind, criterion_results)
        items_out.append(
            {
                "id": iid,
                "title": title,
                "category": category,
                "kind": kind,
                "doc_href": doc_href,
                "action_hint": action_hint,
                "sot_refs": sot_refs,
                "display_status": display,
                "criterion_results": criterion_results,
                "max_days_in_waiting": max_days_in_waiting,
                "max_days_in_ready_attention": max_days_in_ready_attention,
            }
        )
    summary = {
        "ready": sum(1 for x in items_out if x["display_status"] == "ready"),
        "waiting": sum(1 for x in items_out if x["display_status"] == "waiting"),
        "ready_attention": sum(
            1 for x in items_out if x["display_status"] == "ready_attention"
        ),
        "blocked_external": sum(
            1 for x in items_out if x["display_status"] == "blocked_external"
        ),
    }
    return {
        "registry_version": data.get("registry_version", 0),
        "evaluation_profile": prof,
        "items_total_in_registry": len(all_raw),
        "items_in_profile": len(items_out),
        "evaluation_profiles_help": data.get("evaluation_profiles", {}),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root.resolve()),
        "default_script_timeout": default_script_timeout,
        "summary": summary,
        "items": items_out,
    }


def merge_aging_timestamps(
    prev_display: dict[str, str],
    items: list[dict[str, Any]],
    prev_aging: dict[str, Any],
    now_iso: str,
) -> dict[str, Any]:
    """
    Track when each item entered ``waiting`` or ``ready_attention`` (per profile).
    Re-entering a column resets the clock. Leaving removes the id from that map.
    """
    prev_w = prev_aging.get("waiting") if isinstance(prev_aging, dict) else None
    prev_ra = prev_aging.get("ready_attention") if isinstance(prev_aging, dict) else None
    if not isinstance(prev_w, dict):
        prev_w = {}
    if not isinstance(prev_ra, dict):
        prev_ra = {}
    next_w: dict[str, str] = {}
    next_ra: dict[str, str] = {}
    for it in items:
        iid = str(it.get("id", ""))
        if not iid:
            continue
        st = str(it.get("display_status", ""))
        old = prev_display.get(iid)
        if st == "waiting":
            if old != "waiting":
                next_w[iid] = now_iso
            else:
                next_w[iid] = prev_w.get(iid, now_iso)
        if st == "ready_attention":
            if old != "ready_attention":
                next_ra[iid] = now_iso
            else:
                next_ra[iid] = prev_ra.get(iid, now_iso)
    return {"waiting": next_w, "ready_attention": next_ra}


def _utc_days_since(iso_s: str | None, now: datetime) -> int | None:
    if not iso_s or not str(iso_s).strip():
        return None
    dt = parse_datetime(str(iso_s).strip())
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt.astimezone(timezone.utc)
    return max(0, int(delta.total_seconds() // 86400))


def apply_sla_enrichment(
    payload: dict[str, Any],
    aging: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """
    Mutates each item with days-in-column and breach flags; sets ``sla_summary`` on payload.
    External / blocked rows do not consume waiting SLAs.
    """
    sla_block = registry.get("sla") if isinstance(registry.get("sla"), dict) else {}
    default_w = int(sla_block.get("default_max_days_in_waiting", 21))
    default_ra = int(sla_block.get("default_max_days_in_ready_attention", 45))
    waiting_map = aging.get("waiting") if isinstance(aging.get("waiting"), dict) else {}
    ra_map = (
        aging.get("ready_attention")
        if isinstance(aging.get("ready_attention"), dict)
        else {}
    )
    now = datetime.now(timezone.utc)
    breached_w = 0
    breached_ra = 0
    for it in payload.get("items") or []:
        iid = str(it.get("id", ""))
        st = str(it.get("display_status", ""))
        kind = str(it.get("kind", ""))
        if kind == "external_blocker" or st == "blocked_external":
            it["sla_waiting_since"] = None
            it["sla_ready_attention_since"] = None
            it["days_in_waiting"] = None
            it["days_in_ready_attention"] = None
            it["sla_waiting_breached"] = False
            it["sla_ready_attention_breached"] = False
            continue
        it["sla_waiting_since"] = waiting_map.get(iid)
        it["sla_ready_attention_since"] = ra_map.get(iid)
        max_w = it.get("max_days_in_waiting")
        try:
            max_w_i = int(max_w) if max_w is not None else default_w
        except (TypeError, ValueError):
            max_w_i = default_w
        max_ra = it.get("max_days_in_ready_attention")
        try:
            max_ra_i = int(max_ra) if max_ra is not None else default_ra
        except (TypeError, ValueError):
            max_ra_i = default_ra
        it["sla_waiting_max_days"] = max_w_i
        it["sla_ready_attention_max_days"] = max_ra_i
        dw = _utc_days_since(it["sla_waiting_since"], now) if st == "waiting" else None
        dra = (
            _utc_days_since(it["sla_ready_attention_since"], now)
            if st == "ready_attention"
            else None
        )
        it["days_in_waiting"] = dw
        it["days_in_ready_attention"] = dra
        wb = bool(dw is not None and dw > max_w_i and st == "waiting")
        rab = bool(dra is not None and dra > max_ra_i and st == "ready_attention")
        it["sla_waiting_breached"] = wb
        it["sla_ready_attention_breached"] = rab
        if wb:
            breached_w += 1
        if rab:
            breached_ra += 1
    payload["sla_summary"] = {
        "default_max_days_in_waiting": default_w,
        "default_max_days_in_ready_attention": default_ra,
        "breached_waiting": breached_w,
        "breached_ready_attention": breached_ra,
    }
    return payload


def diff_emit_ready_transitions(
    previous: dict[str, str],
    current: dict[str, str],
) -> list[tuple[str, str, str]]:
    """
    Return list of (item_id, prev_status, new_status) for items that became
    ready or ready_attention from a non-terminal positive state (typically waiting).
    """
    out: list[tuple[str, str, str]] = []
    for iid, new_st in current.items():
        old_st = previous.get(iid)
        if new_st not in ("ready", "ready_attention"):
            continue
        if old_st == new_st:
            continue
        if old_st is None:
            continue
        if old_st == "waiting" or (
            old_st == "ready_attention" and new_st == "ready"
        ):
            out.append((iid, old_st or "", new_st))
    return out
