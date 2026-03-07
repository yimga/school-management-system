from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def build_term_report_pdf(
    *,
    student_name: str,
    student_code: str,
    year_name: str,
    term_name: str,
    rows: list[dict],
    overall: float | None,
    promotion_status: str | None = None,
):
    """
    rows: [{subject, coef, test1, test2, avg}]
    returns: bytes (PDF)
    """
    buff = BytesIO()
    c = canvas.Canvas(buff, pagesize=letter)
    width, height = letter

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Student Term Report")
    y -= 25

    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Student: {student_name}  ({student_code})")
    y -= 16
    c.drawString(50, y, f"Academic Year: {year_name}")
    y -= 16
    c.drawString(50, y, f"Term: {term_name}")
    y -= 22

    # Table header
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Subject")
    c.drawString(260, y, "Coef")
    c.drawString(310, y, "Test1")
    c.drawString(370, y, "Test2")
    c.drawString(430, y, "Average")
    y -= 12
    c.line(50, y, 550, y)
    y -= 16

    c.setFont("Helvetica", 10)
    for r in rows:
        if y < 80:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)

        c.drawString(50, y, str(r.get("subject", ""))[:35])
        c.drawString(260, y, str(r.get("coef", "")))
        c.drawString(310, y, str(r.get("test1", "")))
        c.drawString(370, y, str(r.get("test2", "")))
        c.drawString(430, y, str(r.get("avg", "")))
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, f"Overall: {overall if overall is not None else 'N/A'}")
    if promotion_status:
        y -= 16
        c.drawString(50, y, f"Status: {promotion_status}")

    c.showPage()
    c.save()
    return buff.getvalue()
