from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    lock = json.loads(read("var/admin-approval-build-lock.json"))
    base_site = read("templates/admin/base_site.html")
    css = read("static/css/rmc-admin-emergency-full-canvas-v17.css")
    css_n = re.sub(r"\s+", "", css)
    errors: list[str] = []

    for preview in lock.get("approval_previews", []):
        if not (ROOT / preview).is_file():
            errors.append(f"approval preview missing: {preview}")
    proof_sources = [base_site, css]
    proof_sources.extend(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "templates/admin").rglob("*.html")
    )
    proof_sources.extend(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "static/js").glob("rmc-admin-*.js")
    )
    proof_haystack = "\n".join(proof_sources)
    for proof in lock.get("visible_proofs", []):
        if proof not in proof_haystack:
            errors.append(f"visible proof missing from live shell: {proof!r}")

    required = (
        "minmax(0,1fr)minmax(9.2rem,17%)2.35rem",
        "minmax(0,1fr)minmax(9.5rem,18%)2.35rem",
        "@media(max-width:1024px)",
        "grid-template-columns:minmax(0,1fr)!important",
    )
    for marker in required:
        if marker not in css_n:
            errors.append(f"approved responsive geometry missing: {marker}")

    for template, marker in {
        "templates/admin/index_superadmin.html": 'data-rmc-admin-archetype="discover"',
        "templates/admin/index_tenant.html": 'data-rmc-admin-archetype="discover"',
        "templates/admin/change_list.html": 'data-rmc-admin-archetype="scan"',
        "templates/admin/change_form.html": 'data-rmc-admin-archetype="edit"',
        "templates/admin/object_history.html": 'data-rmc-admin-archetype="audit"',
        "templates/admin/delete_confirmation.html": 'data-rmc-admin-archetype="decide"',
    }.items():
        if marker not in read(template):
            errors.append(f"{template} missing {marker}")

    if errors:
        print("PREVIEW_PARITY_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PREVIEW_PARITY_PASS")
    print(f"build={lock['build_id']} approvals={len(lock['approval_previews'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
