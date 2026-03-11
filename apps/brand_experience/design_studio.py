"""
Phase 10 — 10.5: Design Studio stub.
Split document vs experience design; layout metadata and layout builder.
When implemented: layout_metadata for templates, layout builder UI.
"""


def get_layout_metadata(layout_key: str, variant: str | None = None) -> dict:
    """
    Return layout metadata for a given key (document or experience layout).
    Resolves from ExperiencePack when available; otherwise returns minimal structure.
    """
    out = {"key": layout_key, "variant": variant, "sections": []}
    try:
        from apps.packages.models import ExperiencePack
        ep = ExperiencePack.objects.filter(code=layout_key, is_active=True).first()
        if ep and getattr(ep, "layout_schema", None):
            schema = ep.layout_schema if isinstance(ep.layout_schema, dict) else {}
            out["sections"] = schema.get("sections", []) if isinstance(schema.get("sections"), list) else []
    except Exception:
        pass
    return out


def get_document_layout_schema(layout_key: str) -> dict:
    """Document-only layout schema (sections, blocks)."""
    meta = get_layout_metadata(layout_key)
    return {"key": layout_key, "sections": meta.get("sections", []), "blocks": []}
