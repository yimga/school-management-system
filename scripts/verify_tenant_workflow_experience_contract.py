from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    partial = _read("templates/partials/tenant/workflow_portal.html")
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
        _require(token in role_home_css, f"workflow role-home css missing {token}", failures)

    for rel in (
        "templates/parent/workflow_center.html",
        "templates/teacher/workflow_center.html",
        "templates/student/workflow_center.html",
    ):
        text = _read(rel)
        _require(
            'data-rmc-page-fold-nav="required"' in text,
            f"{rel} must declare page-fold nav",
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
