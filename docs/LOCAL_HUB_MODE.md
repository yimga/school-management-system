# Local Hub Mode and dual deployment (online + edge)

**Sovereign delivery program:** Full offline/online + email + Field Client roadmap — [`docs/plans/SOVEREIGN_OFFLINE_ONLINE_DELIVERY_PLATFORM_PLAN.md`](plans/SOVEREIGN_OFFLINE_ONLINE_DELIVERY_PLATFORM_PLAN.md) (SOT batch **1405**).

AI routing (cloud vs Ollama vs guided): **[AI_DEPLOYMENT_POSTURE.md](AI_DEPLOYMENT_POSTURE.md)**.

RunMyCampus supports **two connectivity profiles** with one codebase:

| Profile | `RMC_DEPLOYMENT_PROFILE` | Server | Offline school ops | Live AI |
| --- | --- | --- | --- | --- |
| **Online (SaaS)** | `online` (default) | Render (`*.runmycampus.com`) | Queue on device → sync when Render is reachable | Cloud API via `LITELLM_*` and/or **rules** fallback (no extra VM) |
| **Edge (LAN hub)** | `edge` | Django on school LAN | Same PWA queue → sync to **hub** URL | Optional **Ollama on hub**; else rules on hub |
| **Hybrid** | `hybrid` | Render + optional hub | Cloud primary; SW may retry `hub_base_url` when cloud fetch fails | Cloud when up; hub Ollama when on LAN |

**Offline mode is school operations** (attendance, grades, forms, payments) — **not** on-device LLM. Teachers need connectivity to **their origin** (Render or hub) to sync; the browser can queue work while offline.

See also: [RESILIENT_EDGE_IMPLEMENTATION_STATUS.md](RESILIENT_EDGE_IMPLEMENTATION_STATUS.md), [OLLAMA_OPERATIONS_AND_UPDATES.md](OLLAMA_OPERATIONS_AND_UPDATES.md).

---

## Online (SaaS) — Render, no extra node

### Operator setup

1. **Env on Render** (Dashboard secrets):

   ```bash
   RMC_DEPLOYMENT_PROFILE=online
   RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=1
   AI_ALLOW_RULES_FALLBACK=1
   # Optional cloud AI (no separate LiteLLM VM if provider exposes OpenAI-compatible URL):
   # LITELLM_PROXY_URL=https://your-proxy-or-azure-endpoint/v1
   # LITELLM_API_KEY=...
   # LITELLM_MODEL=gemini/gemini-2.0-flash
   # Embeddings on cloud (optional):
   # AI_EMBEDDING_BACKEND=openai_compatible
   # AI_EMBEDDING_ENDPOINT=...
   # AI_EMBEDDING_API_KEY=...
   ```

2. **New schools** receive the offline bundle automatically at end of provisioning (`maybe_apply_offline_bundle_on_provision`).

3. **Existing schools:**

   ```bash
   python manage.py apply_offline_mode_bundle --all-active
   ```

4. **Staff rollout:** log in once, Add to Home Screen (PWA), stay on Wi‑Fi until prefetch completes; use **Sync now** in the header bar when back online.

### What “offline” means on Render

- Device loses internet → queued writes in service worker + Dexie mirror.
- Device regains internet **to Render** → **Sync now** posts to `/api/offline/delta/` and related APIs.
- AI Center needs the server; without Render, **rules/KB degraded mode** only if the user had loaded the app while online (no new AI calls).

---

## Edge (LAN hub) — no cloud day-to-day

### Concept

- **Hub device**: Raspberry Pi, laptop, or desktop on school Wi‑Fi runs Django (and optionally Ollama).
- Reachable at e.g. `http://192.168.1.100:8000/` or `http://sms-hub.local/`.
- **Client devices** use **only** the hub URL (bookmark / PWA). LAN access to the hub counts as “online” for the app.

### Hub install (outline)

```bash
bash scripts/install_local_hub.sh
# then:
export RMC_DEPLOYMENT_PROFILE=edge
python manage.py runserver 0.0.0.0:8000
```

Or manually:

1. Clone repo, `.venv`, `pip install -r requirements.txt`, `migrate`, `ensure_superuser`.
2. Set `RMC_DEPLOYMENT_PROFILE=edge` in `.env`.
3. Bind app to `0.0.0.0`; fixed DHCP for hub IP; firewall allows port 8000 on LAN.
4. Create school (wizard or admin); `python manage.py apply_offline_mode_bundle --school-id <uuid>`.
5. Optional: `ollama serve` + `ollama create ai-center-master -f ai/Modelfile`; `OLLAMA_BASE_URL=http://127.0.0.1:11434`.

### Security and data

- Hub holds the database; restrict physical and LAN access.
- Prefer HTTPS on LAN where possible.
- Back up hub DB regularly; central sync to Render is an **operator process** (export/restore), not automatic in v1.

---

## Hybrid — Render primary, hub fallback

1. Production on Render as today.
2. Hub at school with copy of tenant DB (ops procedure).
3. Render env:

   ```bash
   RMC_DEPLOYMENT_PROFILE=hybrid
   RMC_HUB_BASE_URL=http://192.168.1.100:8000
   ```

4. Per-tenant **Feature Control** → `hub_base_url` (or bundle apply with `--hub-base-url`).
5. Service worker retries hub when main-origin fetch fails (`SMS_OFFLINE_CONFIG.hubBaseUrl`).

**Note:** Cookies are per-origin; users may need to use hub URL directly when cloud is down for extended periods.

---

## Canonical offline feature bundle

Applied via `apps/platform_runtime/offline_mode_bundle.py`:

- `enable_offline_mode` (Feature Control / RuntimeDefaults)
- `offline_mode` in `School.features` (Policy Registry module gate — required for `OFFLINE_ENABLED_FOR_CURRENT_SCHOOL` in templates)
- `enable_offline_form_queue`, `enable_offline_attendance_sync`, `enable_offline_grade_sync`, `enable_offline_payment_sync`, `enable_offline_background_sync`
- `show_offline_status_bar`, `offline_entity_sync`, `offline_requests_sync`
- `request_persistent_browser_storage`, `reachability_url=/health/`

Management command:

```bash
python manage.py apply_offline_mode_bundle --school-id <uuid>
python manage.py apply_offline_mode_bundle --all-active --dry-run
python manage.py apply_offline_mode_bundle --school-id <uuid> --hub-base-url http://192.168.1.10:8000
```

Verifier:

```bash
python scripts/verify_online_edge_dual_mode.py
```

---

## AI posture (both profiles)

| Situation | Behavior |
| --- | --- |
| Online + cloud configured | Selected tasks may use `litellm` tier (PII-gated). |
| Online + no cloud | **Intelligent rules** + KB RAG (`AI_ALLOW_RULES_FALLBACK=1`). |
| Edge hub + Ollama | Live model when device reaches hub. |
| Browser offline | No new AI; queued **school ops** only. |

`general_chat` remains **`ollama` → `rules`** by default; add cloud tiers only via `AI_GATEWAY_TASK_TIERS` after legal review.

---

## Client checklist (per school)

1. Confirm `enable_offline_mode` on (Feature Control or bundle command).
2. Each role device: login → PWA install → prefetch on good network.
3. Train: **Sync now**, offline queue page, conflict resolution.
4. Document origin URL (Render vs hub) on the staff quick-start card.

---

## Summary

- **No code fork** for edge: same repo, different env + URL.
- **Online + offline mode** = resilient SaaS with PWA queue.
- **Edge** = hub is the server; cloud optional for backup.
- **AI** stays server-side; plan cloud API on Render or Ollama on hub — not on student phones offline.
