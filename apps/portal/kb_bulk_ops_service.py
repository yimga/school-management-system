"""One-click manager wrappers for KB bulk CLI commands."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command


def _capture_command(command: str, **options) -> dict[str, str]:
    stdout_buf = StringIO()
    stderr_buf = StringIO()
    call_command(command, stdout=stdout_buf, stderr=stderr_buf, **options)
    return {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
    }


def run_import_docs_to_kb(
    *,
    category: str = "system-admin",
    overwrite: bool = False,
    dry_run: bool = False,
    include_root: bool = False,
    generate_odt: bool = False,
    odt_engine: str = "auto",
) -> dict[str, str]:
    """Run ``import_docs_to_kb`` and return captured stdout/stderr."""
    options: dict = {"category": category, "odt_engine": odt_engine}
    if overwrite:
        options["overwrite"] = True
    if dry_run:
        options["dry_run"] = True
    if include_root:
        options["include_root"] = True
    if generate_odt:
        options["generate_odt"] = True
    return _capture_command("import_docs_to_kb", **options)


def run_generate_kb_odt(
    *,
    article_slug: str = "",
    engine: str = "auto",
    formats: str = "odt",
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, str]:
    """Run ``generate_kb_odt`` for all articles or one slug."""
    options: dict = {"engine": engine, "formats": formats}
    if article_slug:
        options["article_slug"] = article_slug.strip()
    else:
        options["all"] = True
    if dry_run:
        options["dry_run"] = True
    if overwrite:
        options["overwrite"] = True
    return _capture_command("generate_kb_odt", **options)
