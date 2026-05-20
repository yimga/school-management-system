"""
AST-backed code snippets for operator/staff support (not exposed to student/parent RAG).
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "docs" / "generated" / "code_support_index.json"
STAFF_VISIBILITY = {"staff", "operator"}
SKIP_PARTS = {"migrations", "tests", "__pycache__", ".venv", "node_modules"}


def _visibility_for_path(rel: str) -> str:
    low = rel.replace("\\", "/").lower()
    if "payroll" in low or "finance" in low and "student" not in low:
        return "staff"
    if "super" in low or "migration_cloud" in low or "manager" in low:
        return "operator"
    return "staff"


def _chunk_python_file(path: Path) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        logger.debug("skip %s: %s", path, exc)
        return []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    chunks: list[dict[str, Any]] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1) or start + 1
            snippet = "\n".join(lines[start:end])[:1200]
            chunks.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "file": rel,
                    "line_start": node.lineno,
                    "line_end": end,
                    "visibility": _visibility_for_path(rel),
                    "text": snippet,
                }
            )
        elif isinstance(node, ast.ClassDef):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1) or start + 1
            snippet = "\n".join(lines[start:end])[:1200]
            chunks.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "file": rel,
                    "line_start": node.lineno,
                    "line_end": end,
                    "visibility": _visibility_for_path(rel),
                    "text": snippet,
                }
            )
    return chunks[:40]


def build_code_support_index(
    *,
    apps_only: bool = True,
    max_files: int = 400,
) -> dict[str, Any]:
    roots = [ROOT / "apps", ROOT / "services"] if apps_only else [ROOT]
    all_chunks: list[dict[str, Any]] = []
    seen_files = 0
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in path.parts for part in SKIP_PARTS):
                continue
            seen_files += 1
            if seen_files > max_files:
                break
            all_chunks.extend(_chunk_python_file(path))
    return {
        "chunk_count": len(all_chunks),
        "file_count": seen_files,
        "chunks": all_chunks,
    }


def write_code_support_index(path: Path | None = None) -> Path:
    out_path = path or DEFAULT_OUTPUT
    payload = build_code_support_index()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def search_code_index(
    query: str,
    *,
    limit: int = 3,
    visibility: str = "staff",
) -> list[str]:
    """Return plain-text lines for staff/operator troubleshooting context."""
    path = DEFAULT_OUTPUT
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    tokens = [t.lower() for t in (query or "").split() if len(t) > 3][:8]
    if not tokens:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in payload.get("chunks") or []:
        vis = chunk.get("visibility") or "staff"
        if visibility == "operator" and vis not in STAFF_VISIBILITY:
            continue
        if visibility == "staff" and vis == "operator":
            continue
        hay = f"{chunk.get('file','')} {chunk.get('name','')} {chunk.get('text','')}".lower()
        score = sum(1 for t in tokens if t in hay)
        if score:
            scored.append((float(score), chunk))
    scored.sort(key=lambda row: row[0], reverse=True)
    lines: list[str] = []
    for score, chunk in scored[:limit]:
        lines.append(
            f"- CODE [{score:.0f}]: {chunk.get('file')}:{chunk.get('line_start')} "
            f"{chunk.get('kind')} {chunk.get('name')}"
        )
    return lines
