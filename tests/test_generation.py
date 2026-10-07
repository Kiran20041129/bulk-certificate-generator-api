import io
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.core.exceptions import CertificateGenerationError, TemplateNotFoundError
from app.services.pdf_service import (
    CertificateData,
    CertificateRenderer,
    fit_font_size,
    format_date,
)
from tests.helpers import make_payload

JOBS_URL = "/api/v1/certificates/jobs"


def sample_data(name: str = "Kiran Naidu") -> CertificateData:
    return CertificateData(name, "AI Workshop 2026", date(2026, 10, 7), "CERT-TEST123456")


# ---- Renderer unit tests ----
def test_renderer_creates_a_pdf_with_the_recipient_details(real_renderer, tmp_path):
    output = real_renderer.render(sample_data(), tmp_path / "out" / "cert.pdf")

    assert output.is_file()
    assert output.read_bytes().startswith(b"%PDF")
    reader = PdfReader(str(output))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for expected in ("Kiran Naidu", "AI Workshop 2026", "7 October 2026", "CERT-TEST123456"):
        assert expected in text


def test_renderer_keeps_template_text(real_renderer, tmp_path):
    output = real_renderer.render(sample_data(), tmp_path / "cert.pdf")
    assert "CERTIFICATE" in PdfReader(str(output)).pages[0].extract_text()


def test_renderer_handles_accented_names(real_renderer, tmp_path):
    output = real_renderer.render(sample_data("José Fernández"), tmp_path / "cert.pdf")
    assert "José Fernández" in PdfReader(str(output)).pages[0].extract_text()


def test_renderer_shrinks_long_names_to_fit(real_renderer, tmp_path):
    long_name = "Maximilian Alexander Montgomery-Wellington Fitzgerald III"
    assert fit_font_size(long_name, "Times-BoldItalic", 38, 480) < 38
    assert real_renderer.render(sample_data(long_name), tmp_path / "cert.pdf").is_file()


def test_renderer_rejects_unsupported_characters(real_renderer, tmp_path):
    with pytest.raises(CertificateGenerationError):
        real_renderer.render(sample_data("राहुल"), tmp_path / "cert.pdf")


def test_renderer_raises_when_template_is_missing(tmp_path):
    renderer = CertificateRenderer(Path(tmp_path / "does_not_exist.pdf"))
    with pytest.raises(TemplateNotFoundError):
        renderer.render(sample_data(), tmp_path / "cert.pdf")


def test_format_date():
    assert format_date(date(2026, 10, 7)) == "7 October 2026"


# ---- Through the API ----
def test_job_generates_one_pdf_per_valid_recipient(client, output_dir):
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob", "Carol")).json()["job_id"]

    certificates = client.get(f"{JOBS_URL}/{job_id}/certificates").json()["certificates"]

    assert all(c["status"] == "success" for c in certificates)
    pdf_files = list((output_dir / f"job_{job_id}").glob("*.pdf"))
    assert len(pdf_files) == 3


def test_certificate_ids_are_unique_and_printed_on_the_pdf(client):
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob")).json()["job_id"]
    certificates = client.get(f"{JOBS_URL}/{job_id}/certificates").json()["certificates"]

    codes = [c["certificate_code"] for c in certificates]
    assert len(set(codes)) == 2
    assert all(code.startswith("CERT-") for code in codes)

    pdf = client.get(f"/api/v1/certificates/{certificates[0]['certificate_id']}")
    text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert codes[0] in text
