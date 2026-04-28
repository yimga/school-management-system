# Webhook Event Catalog

RunMyCampus integration events are defined in `apps/platform_runtime/events.py` (`EVENT_CATALOG`).

## Contract
- Each event has a stable `event_type` and payload schema hint list.
- All events include tenant context and support optional idempotency keys.
- Unsupported event types are ignored by `emit_platform_event()` (no implicit creation).

## Extension workflow
- Marketplace/integration packs should declare webhook subscriptions against catalog names only.
- Extension surfaces are listed in `apps/marketplace/extension_registry.py`.
- Public API reference remains in `docs/DEVELOPER_PUBLIC_API.md`.

