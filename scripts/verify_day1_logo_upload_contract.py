#!/usr/bin/env python3
"""Verifier: Day-1 Act-1 live logo upload contract (batch 1372, agent R3).

Asserts the structural contract of the live logo-upload widget shipped
alongside the existing 3-act Day-1 Magic sequence. Exit code 0 on PASS;
1 on FAIL with a brief findings table.

Checks:
  1. ``Day1MagicService.accept_logo_upload`` is defined in the service.
  2. ``LogoUploadResult`` dataclass is defined and re-exported.
  3. ``TenantStudioDay1Act1LogoUploadView`` exists in the views module.
  4. URL name ``tenant_studio_day1_act1_logo_upload`` is wired.
  5. Act 1 partial conditionally renders the upload widget only when the
     school has no logo -- resolved by walking the template's {% if %} nesting
     to the widget root and then confirming the gating variable is a logo
     signal the Act-1 view actually supplies. (Do NOT re-pin a literal here:
     the gate used to demand `{% if not school.logo_url %}` and stayed red for
     free after the view started passing a resolved `logo_display_url`.)
  6. CSS file carries upload-zone / preview / error styles.
  7. JS file carries the drag-and-drop handlers + fetch submitter +
     custom-event dispatch.
  8. View carries the ``# rbac-allow:`` marker for the upload action.
  9. CSRF protection is NOT bypassed (no ``csrf_exempt`` decorator).
 10. MIME sniffing happens via the LogoUploadValidator (not extension).
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _exists(rel: str) -> bool:
    return (REPO / rel).is_file()


_TAG_RE = re.compile(
    r"{%\s*(if|elif|else|endif)\b\s*(.*?)\s*%}"
    r"|(data-rmc-day1-logo-upload(?![-\w]))"
)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _upload_widget_gate(partial_text: str) -> tuple[str | None, str]:
    """Return (variable the upload widget root is gated on, diagnostic).

    Walks {% if %}/{% elif %}/{% else %}/{% endif %} nesting and reports the
    conditions in force where ``data-rmc-day1-logo-upload`` (the widget root
    attribute) appears. A structural walk, not a string match: renaming the
    context variable must not silently disarm this check, and must not keep it
    red once the rename is legitimate.
    """
    stack: list[str | None] = []
    for match in _TAG_RE.finditer(partial_text):
        anchor = match.group(3)
        if anchor:
            if not stack:
                return None, "widget root is not inside any {% if %}"
            active = [cond for cond in stack if cond]
            negated = [
                cond[4:].strip()
                for cond in active
                if cond.startswith("not ") and _NAME_RE.match(cond[4:].strip())
            ]
            if not negated:
                return None, f"enclosing conditions are {active or ['{% else %}']}"
            return negated[-1], "ok"
        tag, expr = match.group(1), match.group(2)
        if tag == "if":
            stack.append(expr)
        elif tag == "elif":
            if stack:
                stack[-1] = expr
        elif tag == "else":
            if stack:
                stack[-1] = None
        elif tag == "endif":
            if stack:
                stack.pop()
    return None, "widget root attribute data-rmc-day1-logo-upload not found"


def _view_supplies_logo_gate(views_text: str, class_name: str, var: str) -> list[str]:
    """Confirm ``var`` is a logo-derived context value of ``class_name``."""
    problems: list[str] = []
    try:
        tree = ast.parse(views_text)
    except SyntaxError as exc:  # pragma: no cover - views module must parse
        return [f"views module does not parse: {exc}"]
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if node is None:
        return [f"views module has no {class_name}"]
    in_context = any(
        isinstance(d, ast.Dict)
        and any(
            isinstance(k, ast.Constant) and k.value == var for k in d.keys
        )
        for d in ast.walk(node)
    )
    if not in_context:
        problems.append(
            f"{class_name} does not pass {var!r} in the Act-1 template context"
        )
    sources = [
        ast.get_source_segment(views_text, a.value) or ""
        for a in ast.walk(node)
        if isinstance(a, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == var for t in a.targets)
    ]
    if not sources:
        problems.append(f"{class_name} never assigns {var!r}")
    elif not any("logo" in s for s in sources):
        problems.append(
            f"{class_name} assigns {var!r} from something with no logo signal: "
            f"{sources!r}"
        )
    return problems


def main() -> int:
    findings: list[str] = []

    # 1. Service-layer surface.
    service_text = _text("apps/siteconfig/tenant_studio_day1.py")
    for symbol in (
        "def accept_logo_upload",
        "class LogoUploadResult",
        "DAY1_DEFAULT_LOGO_MAX_BYTES",
        "_persist_day1_logo_bytes",
        "_classify_logo_validation_failure",
    ):
        if symbol not in service_text:
            findings.append(f"day1 service missing symbol: {symbol}")

    # 2. View-layer surface.
    views_text = _text("apps/siteconfig/views_tenant_studio_hub.py")
    for symbol in (
        "class TenantStudioDay1Act1LogoUploadView",
        "rbac-allow: tenant-admin-or-staff-day1-logo-upload",
        "_resolve_logo_max_bytes",
        "_read_upload_bounded",
    ):
        if symbol not in views_text:
            findings.append(f"views module missing symbol: {symbol}")
    # Catch active csrf_exempt application (decorator or method_decorator)
    # while tolerating prose mentions in docstrings.
    if re.search(r"^\s*@csrf_exempt", views_text, re.MULTILINE) or "method_decorator(csrf_exempt" in views_text:
        findings.append(
            "views module applies csrf_exempt — the upload view must remain CSRF-protected"
        )

    # 3. URL wiring.
    urls_text = _text("apps/siteconfig/urls.py")
    if "tenant_studio_day1_act1_logo_upload" not in urls_text:
        findings.append("url name not wired: tenant_studio_day1_act1_logo_upload")
    if "TenantStudioDay1Act1LogoUploadView" not in urls_text:
        findings.append("urls.py does not import TenantStudioDay1Act1LogoUploadView")
    if "studio/day1/act1/logo-upload/" not in urls_text:
        findings.append("urls.py does not declare the studio/day1/act1/logo-upload/ path")

    # 4. Act 1 partial — conditional upload widget.
    act1_partial = _text("templates/siteconfig/partials/tenant_studio_day1_act1_brand.html")
    gate_var, gate_note = _upload_widget_gate(act1_partial)
    if gate_var is None:
        findings.append(
            "Act 1 partial does not gate the upload widget on an absent logo "
            f"({gate_note})"
        )
    elif "logo" not in gate_var:
        findings.append(
            f"Act 1 partial gates the upload widget on {gate_var!r}, which is not "
            "a logo signal"
        )
    elif "." in gate_var:
        findings.append(
            f"Act 1 partial gates the upload widget on {gate_var!r}; the view must "
            "resolve the displayable logo URL so an inline data-URI logo also "
            "suppresses the widget"
        )
    else:
        findings.extend(
            _view_supplies_logo_gate(
                views_text, "TenantStudioDay1Act1View", gate_var
            )
        )
    for hook in (
        "data-rmc-day1-logo-upload",
        "data-rmc-day1-logo-upload-zone",
        "data-rmc-day1-logo-upload-input",
        "data-rmc-day1-logo-upload-form",
        "data-rmc-day1-logo-preview",
        "data-rmc-day1-logo-error",
        "{% csrf_token %}",
    ):
        if hook not in act1_partial:
            findings.append(f"Act 1 partial missing data-hook / token: {hook}")
    if 'accept="image/png,image/jpeg,image/webp"' not in act1_partial:
        findings.append(
            "Act 1 partial does not constrain the file picker to PNG/JPEG/WebP"
        )

    # 5. CSS surface.
    css_text = _text("static/css/tenant-studio-day1.css")
    for css_class in (
        ".rmc-day1-logo-upload-zone",
        ".rmc-day1-logo-preview",
        ".rmc-day1-logo-error",
        ".rmc-day1-logo-upload-zone.is-dragover",
    ):
        if css_class not in css_text:
            findings.append(f"CSS missing rule: {css_class}")

    # 6. JS surface.
    js_text = _text("static/js/rmc-tenant-studio-day1.js")
    for snippet in (
        "wireLogoUpload",
        "submitLogoUpload",
        "rmc:day1:logo-uploaded",
        "ALLOWED_LOGO_MIME",
        "FORBIDDEN_LOGO_MIME",
        "X-CSRFToken",
        'dragover',
        'drop',
    ):
        if snippet not in js_text:
            findings.append(f"JS missing snippet: {snippet}")

    # 7. Service preserves MIME-sniff posture (delegates to LogoUploadValidator).
    if "from apps.schools.school_brand_assets" not in service_text:
        findings.append(
            "service does not import LogoUploadValidator from apps.schools.school_brand_assets"
        )
    if "LogoUploadValidator(image_bytes)" not in service_text:
        findings.append("service does not call LogoUploadValidator(image_bytes)")

    # 8. Tenant isolation: storage path keyed only on school.pk via
    # ``tenant_media_path``. We grep both the service and the marker.
    if "tenant_media_path" not in service_text:
        findings.append("service does not key storage path via tenant_media_path")
    if "tenant-isolation-allow: day1-logo-upload-storage-keyed-on-school-pk-only" not in service_text:
        findings.append("service missing tenant-isolation-allow marker for upload storage")

    print("Day-1 logo upload contract verifier")
    print("=" * 42)
    if findings:
        print(f"FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("PASS — all Day-1 logo upload contract checks succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
