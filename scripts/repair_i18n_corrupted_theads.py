#!/usr/bin/env python3
"""Repair thead rows corrupted by repeated partial trans substitution."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Match a broken thead row: first th is trans-wrapped, then garbage fragments, then plain th cells.
_BROKEN_ROW = re.compile(
    r"<tr>(?P<first><th scope=\"col\">{% trans \"[^\"]+\" %}</th>)(?P<garbage>(?:[^<]*</th>)+)(?P<rest>(?:<th scope=\"col\">[^<]+</th>)*)</tr>",
    re.DOTALL,
)


def _trans_th(label: str) -> str:
    esc = label.replace("\\", "\\\\").replace('"', '\\"')
    return f'<th scope="col">{{% trans "{esc}" %}}</th>'


def repair_row(match: re.Match[str]) -> str:
    rest = match.group("rest")
    labels = re.findall(r"<th scope=\"col\">([^<]+)</th>", rest)
    cells = [match.group("first").replace('{% trans "', '').split('"')[0]]  # wrong approach
    return match.group(0)  # fallback


def repair_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if '%}</th>' not in text or '{% trans "' not in text:
        return False
    original = text

    def fix_row(m: re.Match[str]) -> str:
        row = m.group(0)
        if '%}</th>' not in row and 'Title" %}' not in row:
            return row
        # Extract intended labels from remaining th tags after garbage cleanup.
        labels: list[str] = []
        first = re.search(r'{% trans "([^"]+)" %}', row)
        if first:
            labels.append(first.group(1))
        for lab in re.findall(r'<th scope="col">([^<{]+)</th>', row):
            lab = lab.strip()
            if lab and lab not in labels:
                labels.append(lab)
        if not labels:
            return row
        return "<tr>" + "".join(_trans_th(l) for l in labels) + "</tr>"

    text = re.sub(r"<tr>.*?</tr>", fix_row, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


FIXED_ROWS = {
    "templates/admin/components/theme_preview_section.html": (
        r'<tr><th scope="col">{% trans "Student" %}</th>udent" %}</th>udent" %}</th><th scope="col">Status</th><th scope="col">Balance</th></tr>',
        '<tr><th scope="col">{% trans "Student" %}</th><th scope="col">{% trans "Status" %}</th><th scope="col">{% trans "Balance" %}</th></tr>',
    ),
    "templates/customersuccess/super_dashboard.html": [
        (
            r'<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th>chool" %}</th>chool" %}</th>chool" %}</th><th scope="col">Severity</th><th scope="col">Reason</th><th scope="col">When</th></tr></thead>',
            '<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Severity" %}</th><th scope="col">{% trans "Reason" %}</th><th scope="col">{% trans "When" %}</th></tr></thead>',
        ),
        (
            r'<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th>chool" %}</th>chool" %}</th>chool" %}</th><th scope="col">Category</th><th scope="col">Title</th><th scope="col">When</th></tr></thead>',
            '<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Category" %}</th><th scope="col">{% trans "Title" %}</th><th scope="col">{% trans "When" %}</th></tr></thead>',
        ),
        (
            r'<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th>chool" %}</th>chool" %}</th>chool" %}</th><th scope="col">Workflow</th><th scope="col">Error</th><th scope="col">When</th></tr></thead>',
            '<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Workflow" %}</th><th scope="col">{% trans "Error" %}</th><th scope="col">{% trans "When" %}</th></tr></thead>',
        ),
        (
            r'<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th>chool" %}</th>chool" %}</th>chool" %}</th><th scope="col">Score</th><th scope="col">Dimensions</th><th scope="col">Computed</th></tr></thead>',
            '<thead class="table-light"><tr><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Score" %}</th><th scope="col">{% trans "Dimensions" %}</th><th scope="col">{% trans "Computed" %}</th></tr></thead>',
        ),
    ],
    "templates/feedback/voice_of_customer.html": (
        r'<thead><tr><th scope="col">{% trans "Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th>Title" %}</th><th scope="col">School</th><th scope="col">Role</th><th scope="col">Module</th><th scope="col">Source</th><th scope="col">Support</th><th scope="col">Severity</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "Title" %}</th><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Role" %}</th><th scope="col">{% trans "Module" %}</th><th scope="col">{% trans "Source" %}</th><th scope="col">{% trans "Support" %}</th><th scope="col">{% trans "Severity" %}</th><th scope="col">{% trans "Status" %}</th><th scope="col">{% trans "Action" %}</th></tr></thead>',
    ),
    "templates/platform_runtime/pack_installations.html": (
        r'<thead><tr><th scope="col">{% trans "Pack" %}</th>"Pack" %}</th>"Pack" %}</th>"Pack" %}</th>"Pack" %}</th><th scope="col">Type</th><th scope="col">School</th><th scope="col">Status</th><th scope="col">Applied</th><th scope="col"></th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "Pack" %}</th><th scope="col">{% trans "Type" %}</th><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Status" %}</th><th scope="col">{% trans "Applied" %}</th><th scope="col"></th></tr></thead>',
    ),
    "templates/portal/cahier_list.html": (
        r'<thead><tr><th scope="col">{% trans "Date" %}</th>"Date" %}</th>"Date" %}</th>"Date" %}</th><th scope="col">Class / Subject</th><th scope="col">Title</th><th scope="col">Status</th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "Date" %}</th><th scope="col">{% trans "Class / Subject" %}</th><th scope="col">{% trans "Title" %}</th><th scope="col">{% trans "Status" %}</th></tr></thead>',
    ),
    "templates/portal/office_document_list.html": (
        r'<thead><tr><th scope="col">{% trans "Title" %}</th>Title" %}</th>Title" %}</th><th scope="col">Audience</th><th scope="col">Updated</th><th scope="col"></th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "Title" %}</th><th scope="col">{% trans "Audience" %}</th><th scope="col">{% trans "Updated" %}</th><th scope="col"></th></tr></thead>',
    ),
    "templates/schools/advancement_donor_detail.html": (
        r'<thead><tr><th scope="col">{% trans "Date" %}</th>"Date" %}</th>"Date" %}</th>"Date" %}</th><th scope="col">Amount</th><th scope="col">Campaign</th><th scope="col">{% trans "Fund" %}</th><th scope="col">Notes</th><th scope="col"></th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "Date" %}</th><th scope="col">{% trans "Amount" %}</th><th scope="col">{% trans "Campaign" %}</th><th scope="col">{% trans "Fund" %}</th><th scope="col">{% trans "Notes" %}</th><th scope="col"></th></tr></thead>',
    ),
    "templates/schools/super_pulse.html": [
        (
            r'<thead><tr><th scope="col">{% trans "Region" %}</th>egion" %}</th>egion" %}</th><th scope="col">Schools</th><th scope="col">Students</th></tr></thead>',
            '<thead><tr><th scope="col">{% trans "Region" %}</th><th scope="col">{% trans "Schools" %}</th><th scope="col">{% trans "Students" %}</th></tr></thead>',
        ),
        (
            r'<tr><th scope="col">{% trans "School" %}</th>chool" %}</th>chool" %}</th>chool" %}</th><th scope="col">Slug</th><th scope="col">Students</th><th scope="col">Last activity</th></tr>',
            '<tr><th scope="col">{% trans "School" %}</th><th scope="col">{% trans "Slug" %}</th><th scope="col">{% trans "Students" %}</th><th scope="col">{% trans "Last activity" %}</th></tr>',
        ),
    ],
    "templates/siteconfig/partials/feature_control_ledger_body.html": (
        r'<thead><tr><th scope="col">{% trans "When" %}</th>"When" %}</th>"When" %}</th>"When" %}</th><th scope="col">User</th><th scope="col">Action</th><th scope="col">Changes (summary)</th></tr></thead>',
        '<thead><tr><th scope="col">{% trans "When" %}</th><th scope="col">{% trans "User" %}</th><th scope="col">{% trans "Action" %}</th><th scope="col">{% trans "Changes (summary)" %}</th></tr></thead>',
    ),
}


def main() -> int:
    for rel, spec in FIXED_ROWS.items():
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        pairs = spec if isinstance(spec, list) else [spec]
        for old, new in pairs:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        print("fixed", rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
