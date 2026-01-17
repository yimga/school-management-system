"""Small, shared domain helpers.

Keeping these in one place avoids copy/paste drift across apps.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .models import AcademicYear, Term


def get_active_year_and_term() -> Tuple[Optional[AcademicYear], Optional[Term]]:
    """Return (active_year, active_term) if configured, otherwise (None, None)."""
    year = AcademicYear.objects.filter(is_active=True).first()
    term = Term.objects.filter(is_active=True, academic_year=year).first() if year else None
    return year, term
