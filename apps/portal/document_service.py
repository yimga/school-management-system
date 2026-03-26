"""Central document conversion service (T0/T1/T3).

Single API for Writer/Calc/Impress conversions.
"""

from __future__ import annotations

from pathlib import Path

from .document_conversion import (
    convert_calc_to_ods,
    convert_calc_to_pdf,
    convert_calc_to_xlsx,
    convert_impress_to_odp,
    convert_impress_to_pdf,
    convert_impress_to_pptx,
    convert_to_docx,
    convert_to_odt,
    convert_to_pdf,
)

WRITER_EXTS = {".odt", ".doc", ".docx", ".rtf", ".txt", ".html", ".htm"}
CALC_EXTS = {".ods", ".xls", ".xlsx", ".csv"}
IMPRESS_EXTS = {".odp", ".ppt", ".pptx"}


def infer_document_family(source_path: str) -> str:
    ext = Path(source_path).suffix.lower()
    if ext in CALC_EXTS:
        return "calc"
    if ext in IMPRESS_EXTS:
        return "impress"
    return "writer"


def convert_document(source_path: str, *, target: str, family: str | None = None) -> bytes:
    fam = family or infer_document_family(source_path)
    t = (target or "").strip().lower()

    if fam == "writer":
        if t == "pdf":
            return convert_to_pdf(source_path)
        if t == "docx":
            return convert_to_docx(source_path)
        if t == "odt":
            return convert_to_odt(source_path)
        raise ValueError(f"Unsupported writer target: {target}")

    if fam == "calc":
        if t == "pdf":
            return convert_calc_to_pdf(source_path)
        if t == "xlsx":
            return convert_calc_to_xlsx(source_path)
        if t == "ods":
            return convert_calc_to_ods(source_path)
        raise ValueError(f"Unsupported calc target: {target}")

    if fam == "impress":
        if t == "pdf":
            return convert_impress_to_pdf(source_path)
        if t == "pptx":
            return convert_impress_to_pptx(source_path)
        if t == "odp":
            return convert_impress_to_odp(source_path)
        raise ValueError(f"Unsupported impress target: {target}")

    raise ValueError(f"Unsupported document family: {fam}")
