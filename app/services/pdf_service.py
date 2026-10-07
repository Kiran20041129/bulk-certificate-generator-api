"""Certificate PDF generation.

How it works (the "overlay" technique):
  1. templates/certificate_template.pdf holds the fixed design (borders, titles,
     signature lines). It was produced once by scripts/create_template.py.
  2. For each recipient we draw ONLY the changing text (name, event, date,
     certificate ID) on a blank, transparent page of the same size using
     ReportLab. Positions come from the constants below.
  3. pypdf merges that overlay on top of the template page and saves the result.
"""
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.core.exceptions import CertificateGenerationError, TemplateNotFoundError
from app.utils.text_utils import is_pdf_safe

# ---- Layout: where dynamic text goes on the A4-landscape page (points) ------
# (0, 0) is the bottom-left corner. Shared with scripts/create_template.py so
# the template's lines/labels line up with the text we draw.
PAGE_CENTER_X = 421
NAME_Y, NAME_FONT, NAME_MAX_SIZE, NAME_MAX_WIDTH = 335, "Times-BoldItalic", 38, 480
EVENT_Y, EVENT_FONT, EVENT_MAX_SIZE, EVENT_MAX_WIDTH = 248, "Helvetica-Bold", 24, 520
DATE_Y, DATE_FONT, DATE_SIZE = 190, "Helvetica", 16
CODE_Y, CODE_FONT, CODE_SIZE = 55, "Helvetica", 9
MIN_FONT_SIZE = 10

NAVY = HexColor("#1F3A5F")
GRAY = HexColor("#555555")


@dataclass(frozen=True)
class CertificateData:
    """Everything that changes from one certificate to the next."""

    recipient_name: str
    event_name: str
    event_date: date
    certificate_code: str


def format_date(value: date) -> str:
    return f"{value.day} {value:%B %Y}"  # e.g. "7 October 2026"


def fit_font_size(text: str, font: str, max_size: int, max_width: int) -> int:
    """Shrink the font until the text fits the available width."""
    size = max_size
    while size > MIN_FONT_SIZE and stringWidth(text, font, size) > max_width:
        size -= 1
    if stringWidth(text, font, size) > max_width:
        raise CertificateGenerationError(
            f"Text is too long to fit on the certificate: '{text[:30]}...'"
        )
    return size


class CertificateRenderer:
    """Fills the predefined template with one recipient's details."""

    def __init__(self, template_path: Path) -> None:
        self.template_path = Path(template_path)

    def render(self, data: CertificateData, output_path: Path) -> Path:
        """Create a PDF at `output_path` and return that path."""
        if not self.template_path.is_file():
            raise TemplateNotFoundError(
                "Certificate template is missing; ask an administrator to restore it."
            )
        for label, text in (("name", data.recipient_name), ("event", data.event_name)):
            if not is_pdf_safe(text):
                raise CertificateGenerationError(
                    f"The recipient {label} contains characters the certificate "
                    "font cannot print (only Latin characters are supported)."
                )
        try:
            template_page = PdfReader(str(self.template_path)).pages[0]
            width = float(template_page.mediabox.width)
            height = float(template_page.mediabox.height)
            overlay = self._build_overlay(data, width, height)
            template_page.merge_page(PdfReader(overlay).pages[0])

            writer = PdfWriter()
            writer.add_page(template_page)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as pdf_file:
                writer.write(pdf_file)
        except CertificateGenerationError:
            raise
        except Exception as exc:  # any library/IO problem becomes one clean error
            raise CertificateGenerationError("Could not create the PDF file.") from exc
        return output_path

    @staticmethod
    def _build_overlay(data: CertificateData, width: float, height: float) -> io.BytesIO:
        """Draw the dynamic text on a transparent page the size of the template."""
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(width, height))

        name_size = fit_font_size(data.recipient_name, NAME_FONT, NAME_MAX_SIZE, NAME_MAX_WIDTH)
        pdf.setFillColor(NAVY)
        pdf.setFont(NAME_FONT, name_size)
        pdf.drawCentredString(PAGE_CENTER_X, NAME_Y, data.recipient_name)

        event_size = fit_font_size(data.event_name, EVENT_FONT, EVENT_MAX_SIZE, EVENT_MAX_WIDTH)
        pdf.setFont(EVENT_FONT, event_size)
        pdf.drawCentredString(PAGE_CENTER_X, EVENT_Y, data.event_name)

        pdf.setFillColor(GRAY)
        pdf.setFont(DATE_FONT, DATE_SIZE)
        pdf.drawCentredString(PAGE_CENTER_X, DATE_Y, format_date(data.event_date))

        pdf.setFont(CODE_FONT, CODE_SIZE)
        pdf.drawCentredString(PAGE_CENTER_X, CODE_Y, f"Certificate ID: {data.certificate_code}")

        pdf.save()
        buffer.seek(0)
        return buffer
