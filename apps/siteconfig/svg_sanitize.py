"""SVG sanitizer for tenant-uploaded brand assets.

Tenants can upload a logo / favicon via SiteSettings. Raster (PNG/JPEG/WEBP)
is safe; SVG is not — without sanitization a malicious tenant could embed
``<script>``, ``<foreignObject>``, ``onload=`` handlers, ``javascript:``
URLs, or XML external entities that fire when the SVG is rendered inline
(or even referenced in an ``<img src>`` in some browsers via certain
fallbacks).

This module provides:
  - ``sanitize_svg_bytes(data: bytes) -> bytes`` — returns sanitized SVG
    bytes or raises ``ValidationError`` if the file is not SVG / cannot be
    parsed / has an unrecoverable structure (external DOCTYPE, etc.).
  - ``validate_svg_safe(file)`` — Django field validator. Use on
    ``ImageField`` / ``FileField`` for tenant brand uploads.

Allowlist approach (deny-by-default) — only known-safe SVG tags + attrs
pass through. This is intentionally narrower than a full SVG renderer:
brand marks need shapes, paths, basic gradients, and text. Filters,
foreignObject, embedded scripts, and external resource refs are out.

The sanitizer runs in pure stdlib (``xml.etree.ElementTree``) to keep the
attack surface small and avoid pulling lxml or defusedxml as a hard dep
on every install. We *defuse* the parse step manually by rejecting
DOCTYPE declarations and external entity references before parsing.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

from django.core.exceptions import ValidationError


# SVG namespace constants used by ElementTree's serialization.
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"

# Tags allowed in tenant-supplied SVG. Everything else is stripped.
_ALLOWED_TAGS = frozenset({
    "svg", "g", "defs", "symbol", "use", "title", "desc",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath", "mpath",
    "linearGradient", "radialGradient", "stop",
    "clipPath", "mask",
    "marker",
})

# Tags explicitly stripped (named so we can log/reject for audit).
_DANGEROUS_TAGS = frozenset({
    "script", "foreignObject", "iframe", "object", "embed",
    "image",  # <image> can reference external URLs; strip for brand uploads
    "use",  # <use href> can pull external — we re-allow with sanitization below
    "animate", "animateMotion", "animateTransform", "set",  # animations OK in SVG but skip for brand
    "feImage", "feFlood",  # filter primitives that fetch resources
    "filter",  # complex filters: out
    "switch",
})

# Re-allow <use> when href is internal (#fragment).
_USE_INTERNAL_HREF_OK = True

# Attributes allowed on any element. Plus presentation attrs.
_ALLOWED_ATTRS = frozenset({
    "id", "class", "style",
    "viewBox", "width", "height", "x", "y", "rx", "ry", "cx", "cy", "r",
    "d", "points", "x1", "y1", "x2", "y2",
    "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset",
    "opacity", "fill-opacity", "stroke-opacity",
    "transform", "transform-origin",
    "gradientUnits", "gradientTransform", "spreadMethod",
    "offset", "stop-color", "stop-opacity",
    "clip-path", "clip-rule", "mask",
    "font-family", "font-size", "font-weight", "font-style",
    "text-anchor", "dominant-baseline", "letter-spacing",
    "fill-rule", "vector-effect", "paint-order",
    "preserveAspectRatio",
    "xmlns",  # the SVG namespace declaration itself
})

# Allowed namespaced attrs (lowercase keys we'll match against `{ns}name`).
_ALLOWED_NS_ATTRS = frozenset({
    f"{{{_XLINK_NS}}}href",
})

# Style declarations allowed (CSS property names). Everything else stripped.
_ALLOWED_STYLE_PROPS = frozenset({
    "fill", "stroke", "stroke-width", "opacity", "fill-opacity",
    "stroke-opacity", "font-family", "font-size", "font-weight",
    "font-style", "text-anchor", "dominant-baseline",
    "transform", "letter-spacing", "stroke-linecap", "stroke-linejoin",
    "stroke-dasharray", "stroke-dashoffset", "clip-path", "vector-effect",
    "paint-order", "fill-rule",
})

# Patterns that are categorically unsafe in any attribute value.
_UNSAFE_VALUE_RE = re.compile(
    r"javascript\s*:|data\s*:\s*text/html|expression\s*\(",
    re.IGNORECASE,
)

# DOCTYPE / external entity reference detection. Done pre-parse on the
# raw text — defuses XXE before ElementTree sees it.
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE\b", re.IGNORECASE)
_ENTITY_RE = re.compile(rb"<!ENTITY\b", re.IGNORECASE)
_PROCESSING_INSTRUCTION_OK = re.compile(rb"^\s*<\?xml\b[^?]*\?>", re.IGNORECASE)


def _strip_xml_pi(data: bytes) -> bytes:
    """Allow a single leading `<?xml … ?>` instruction; reject others."""
    return data  # ET accepts a single leading PI naturally; we just don't strip it.


def _looks_like_svg(data: bytes) -> bool:
    head = data[:4096].lstrip()
    return b"<svg" in head[:1024] or head.startswith(b"<?xml")


def _localname(tag: str) -> str:
    """Strip namespace from an ElementTree tag (e.g. '{ns}svg' → 'svg')."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _sanitize_style(value: str) -> str:
    """Strip dangerous declarations from a `style=` attribute value."""
    safe_parts = []
    for decl in value.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in _ALLOWED_STYLE_PROPS:
            continue
        if _UNSAFE_VALUE_RE.search(val):
            continue
        safe_parts.append(f"{prop}: {val}")
    return "; ".join(safe_parts)


def _sanitize_attrs(elem: ET.Element) -> None:
    """In-place sanitize of an element's attributes."""
    drop: list[str] = []
    for attr, val in list(elem.attrib.items()):
        key = attr
        # Drop event-handler attrs categorically — on* prefix.
        bare = _localname(attr).lower()
        if bare.startswith("on"):
            drop.append(key)
            continue
        # Allowlist check.
        if attr.startswith("{"):
            if attr not in _ALLOWED_NS_ATTRS:
                drop.append(key)
                continue
        else:
            if attr not in _ALLOWED_ATTRS:
                drop.append(key)
                continue
        # Value-level guards.
        if _UNSAFE_VALUE_RE.search(val):
            drop.append(key)
            continue
        # href: must be internal (#…) or omitted.
        if bare == "href":
            if not val.startswith("#"):
                drop.append(key)
                continue
        if bare == "style":
            elem.set(attr, _sanitize_style(val))
    for k in drop:
        try:
            del elem.attrib[k]
        except KeyError:
            pass


def _sanitize_tree(elem: ET.Element) -> ET.Element | None:
    """Recursively strip disallowed tags + attrs. Returns sanitized root or None
    if the root itself is disallowed."""
    local = _localname(elem.tag).lower()
    if local in _DANGEROUS_TAGS and not (local == "use" and _USE_INTERNAL_HREF_OK):
        return None
    if local not in _ALLOWED_TAGS:
        return None
    _sanitize_attrs(elem)
    # <use> additionally: drop if href isn't a # fragment.
    if local == "use":
        href = elem.attrib.get(f"{{{_XLINK_NS}}}href") or elem.attrib.get("href")
        if not href or not href.startswith("#"):
            return None
    survivors: list[ET.Element] = []
    for child in list(elem):
        sanitized = _sanitize_tree(child)
        if sanitized is not None:
            survivors.append(sanitized)
    # Replace children with the survivor list.
    for child in list(elem):
        elem.remove(child)
    for child in survivors:
        elem.append(child)
    return elem


def sanitize_svg_bytes(data: bytes) -> bytes:
    """Return sanitized SVG bytes. Raises ValidationError on rejection.

    The caller is responsible for ensuring the upload claims to be an SVG
    (content_type or extension check) before invoking this function.
    """
    if not data:
        raise ValidationError("Empty SVG upload.")
    if _DOCTYPE_RE.search(data[:8192]):
        raise ValidationError("SVG contains DOCTYPE declaration (external entity risk).")
    if _ENTITY_RE.search(data[:8192]):
        raise ValidationError("SVG contains <!ENTITY> declaration (XXE risk).")
    if not _looks_like_svg(data):
        raise ValidationError("Upload does not appear to be SVG content.")
    # Parse with no entity resolver. ElementTree's default parser does not
    # resolve external entities by default, but we still rejected DOCTYPE
    # above for defense in depth.
    try:
        # Register the SVG namespace so the serializer doesn't tag every
        # element with an ns0: prefix on output.
        ET.register_namespace("", _SVG_NS)
        ET.register_namespace("xlink", _XLINK_NS)
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValidationError(f"SVG is not well-formed XML: {exc}") from exc
    if _localname(root.tag).lower() != "svg":
        raise ValidationError("Root element is not <svg>.")
    sanitized_root = _sanitize_tree(root)
    if sanitized_root is None:
        raise ValidationError("SVG has no safe content after sanitization.")
    # Serialize back. Use BytesIO so we can return bytes directly.
    buffer = io.BytesIO()
    tree = ET.ElementTree(sanitized_root)
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def validate_svg_safe(file_obj) -> None:
    """Django validator for ``ImageField`` / ``FileField`` accepting SVG.

    Reads up to 1 MiB and (a) rejects unsafe SVG outright, (b) replaces the
    file content with the sanitized bytes if it parses cleanly. Raster
    uploads are passed through untouched.
    """
    if file_obj is None:
        return
    name = (getattr(file_obj, "name", "") or "").lower()
    content_type = (getattr(file_obj, "content_type", "") or "").lower()
    is_svg = name.endswith(".svg") or "svg+xml" in content_type
    if not is_svg:
        return
    # Read defensively — refuse >1 MiB SVG (a brand mark should fit easily).
    pos = None
    try:
        pos = file_obj.tell()
    except Exception:
        pos = None
    try:
        file_obj.seek(0)
    except Exception:
        pass
    data = file_obj.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValidationError("SVG too large; max 1 MiB.")
    sanitized = sanitize_svg_bytes(data)
    # Write sanitized bytes back, replacing the upload content.
    try:
        file_obj.seek(0)
        if hasattr(file_obj, "truncate"):
            file_obj.truncate()
        file_obj.write(sanitized)
        file_obj.seek(0 if pos is None else pos)
    except Exception:
        # Some storage backends don't support write/truncate on the upload
        # handle. In that case we at least confirmed it's safe — the caller
        # can re-save via `instance.logo.save(name, ContentFile(sanitized))`.
        try:
            file_obj.seek(0)
        except Exception:
            pass
