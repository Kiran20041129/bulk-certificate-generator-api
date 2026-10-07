"""Create templates/certificate_template.pdf (the one predefined template).

Run once:  python scripts/create_template.py
The template only contains the FIXED design. Recipient-specific text is added
later by app/services/pdf_service.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib.colors import HexColor  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.services import pdf_service as layout  # noqa: E402

NAVY, GOLD = HexColor("#1F3A5F"), HexColor("#B8963E")
CREAM, GRAY = HexColor("#FDFBF5"), HexColor("#555555")
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "templates" / "certificate_template.pdf"


def create_template(path: Path = DEFAULT_PATH) -> Path:
    width, height = landscape(A4)
    cx = layout.PAGE_CENTER_X
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=(width, height))
    pdf.setTitle("Certificate Template")

    # Background and double border
    pdf.setFillColor(CREAM)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(6)
    pdf.rect(25, 25, width - 50, height - 50)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.rect(38, 38, width - 76, height - 76)

    # Title
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 46)
    pdf.drawCentredString(cx, 470, "CERTIFICATE")
    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(cx, 438, "OF COMPLETION")
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.line(cx - 120, 422, cx + 120, 422)

    # Fixed sentences + the lines the dynamic text sits on
    pdf.setFillColor(GRAY)
    pdf.setFont("Helvetica-Oblique", 15)
    pdf.drawCentredString(cx, 385, "This certificate is proudly presented to")
    pdf.drawCentredString(cx, 290, "for successfully completing")
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(cx, 212, "Awarded on")
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(1)
    pdf.line(170, layout.NAME_Y - 10, 672, layout.NAME_Y - 10)
    pdf.line(150, layout.EVENT_Y - 10, 692, layout.EVENT_Y - 10)

    # Signature lines
    for x_start, label in ((130, "Program Director"), (532, "Organizer")):
        pdf.line(x_start, 105, x_start + 180, 105)
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(x_start + 90, 90, label)

    # Simple gold seal
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.circle(cx, 115, 28)
    pdf.circle(cx, 115, 22)
    pdf.setFillColor(GOLD)
    pdf.circle(cx, 115, 14, fill=1, stroke=0)

    pdf.save()
    return path


if __name__ == "__main__":
    print(f"Template written to {create_template()}")
