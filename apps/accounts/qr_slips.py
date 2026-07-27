"""Printable QR access slips for self-service join codes.

Renders a join code as a scannable QR (pointing at the school's join page with the
code prefilled) so parents/staff without reliable email can onboard from a printed
poster or hand-out slip — the ParentSquare / K-12 pattern, layered on Feature 2.
"""

from __future__ import annotations

import base64
from io import BytesIO


def qr_png_data_uri(text: str, *, box_size: int = 8, border: int = 2) -> str:
    """Return a self-contained ``data:image/png;base64,...`` QR for ``text``."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        box_size=box_size,
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(text or "")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def join_code_join_url(join_code, *, request=None) -> str:
    """Absolute (or path) URL to the join page with the code prefilled."""
    from django.urls import reverse

    path = reverse("accounts:join_school") + f"?code={join_code.code}"
    return request.build_absolute_uri(path) if request is not None else path
