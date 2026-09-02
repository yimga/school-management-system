from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shell_css_contract as css_contract  # noqa: E402  (repo-local helper)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _css_declares(css_text: str, klass: str) -> bool:
    """True when *klass* is used as a real SELECTOR with declarations.

    `klass in css_text` also matches a comment that merely names the class,
    and it matches any longer identifier that starts with it
    (`.tp-workflow-section-nav-v2`), so a substring test cannot tell a shipped
    rule from prose about a rule.  Comments are stripped, then every
    `selector { body }` pair is inspected: the class must appear in a selector
    as a whole identifier, and that rule must actually declare something.
    """
    stripped = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    whole = re.compile(re.escape(klass) + r"(?![\w-])")
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", stripped):
        selector = match.group(1).split("}")[-1]
        body = match.group(2)
        if ":" not in body:
            continue
        if whole.search(selector):
            return True
    return False


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    # Reachable text, not raw bytes: markup parked behind {% if False %}
    # or inside {% comment %} still spells every token this gate asks for.
    partial = css_contract.reachable_text(
        "templates/partials/tenant/workflow_portal.html"
    )
    service = _read("apps/portal/tenant_workflow_portal.py")
    role_home_css = _read("static/css/rmc-tenant-v3-100x-role-home.css")

    for token in (
        "data-rmc-workflow-contract",
        "data-rmc-readiness-state",
        "data-rmc-blocker-state",
        "data-rmc-help-state",
        "data-rmc-ai-guidance-state",
        "data-rmc-feedback-state",
        "data-rmc-mobile-proof",
        "data-rmc-page-fold-nav",
        "rmc-section-nav",
        "data-rmc-section-anchor",
        "tp-workflow-progress-train",
        "components/pagination.html",
        "data-rmc-mobile-workflow",
        "suppress_command_strip",
    ):
        _require(
            token in partial or token in service,
            f"workflow experience contract missing {token}",
            failures,
        )

    for token in (
        "workflow_contract",
        "steps_page",
        "page_obj",
        "WORKFLOW_STEPS_PER_PAGE",
    ):
        _require(token in service, f"workflow portal service missing {token}", failures)

    for token in (
        ".tp-workflow-section-nav",
        ".tp-workflow-progress-train",
    ):
        _require(
            _css_declares(role_home_css, token),
            f"workflow role-home css missing {token}",
            failures,
        )

    # The page-fold nav is declared once, on the root element of
    # partials/tenant/workflow_portal.html, and every workflow centre includes
    # that partial unconditionally -- so the attribute IS on the rendered page.
    # Grepping each workflow_center.html's own bytes for it reported all three
    # as missing: the assertion was one include shallower than its subject.
    # Resolved against the page's include tree instead, with the inherited
    # shell deliberately left out: templates/portal_base.html stamps the same
    # attribute on every portal page, so following {% extends %} here would
    # make this check pass for anything and never fail.
    for rel in (
        "templates/parent/workflow_center.html",
        "templates/teacher/workflow_center.html",
        "templates/student/workflow_center.html",
    ):
        content = css_contract.content_text(rel)
        _require(
            'data-rmc-page-fold-nav="required"' in content,
            f"{rel} must declare page-fold nav (in its own content tree, "
            f"not inherited from the shell)",
            failures,
        )

    if failures:
        print("verify_tenant_workflow_experience_contract: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("verify_tenant_workflow_experience_contract: TENANT_WORKFLOW_EXPERIENCE_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
