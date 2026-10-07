import io
import zipfile
from pathlib import Path

from tests.helpers import FailingRenderer, make_payload

JOBS_URL = "/api/v1/certificates/jobs"
CERT_URL = "/api/v1/certificates"


def create_job(client, *names) -> int:
    return client.post(JOBS_URL, json=make_payload(*names)).json()["job_id"]


def list_certs(client, job_id) -> list[dict]:
    return client.get(f"{JOBS_URL}/{job_id}/certificates").json()["certificates"]


def test_listing_shows_metadata_and_download_links(client):
    job_id = create_job(client, "Alice", "Bob")

    first = list_certs(client, job_id)[0]

    assert first["recipient_name"] == "Alice"
    assert first["recipient_email"] == "user0@example.com"
    assert first["status"] == "success"
    assert first["file_available"] is True
    assert first["download_url"] == f"{CERT_URL}/{first['certificate_id']}"
    assert first["error_message"] is None


def test_listing_supports_pagination(client):
    job_id = create_job(client, *[f"Person {i}" for i in range(5)])

    page = client.get(f"{JOBS_URL}/{job_id}/certificates", params={"limit": 2, "offset": 2}).json()

    assert page["total"] == 5
    assert [c["recipient_name"] for c in page["certificates"]] == ["Person 2", "Person 3"]


def test_listing_unknown_job_returns_404(client):
    assert client.get(f"{JOBS_URL}/9999/certificates").status_code == 404


def test_download_single_certificate_as_pdf(client):
    job_id = create_job(client, "Alice Smith")
    cert = list_certs(client, job_id)[0]

    response = client.get(f"{CERT_URL}/{cert['certificate_id']}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    disposition = response.headers["content-disposition"]
    assert cert["certificate_code"] in disposition and "Alice_Smith" in disposition


def test_unknown_certificate_returns_404(client):
    assert client.get(f"{CERT_URL}/9999").status_code == 404


def test_failed_certificate_cannot_be_downloaded(client_factory):
    client = client_factory(FailingRenderer(fail_for={"Bob"}))
    job_id = create_job(client, "Alice", "Bob")
    bob = next(c for c in list_certs(client, job_id) if c["recipient_name"] == "Bob")

    response = client.get(f"{CERT_URL}/{bob['certificate_id']}")

    assert response.status_code == 409
    assert "no PDF" in response.json()["detail"]


def test_missing_file_on_disk_returns_404_without_internal_paths(client, output_dir):
    job_id = create_job(client, "Alice")
    cert = list_certs(client, job_id)[0]
    for pdf in Path(output_dir).rglob("*.pdf"):
        pdf.unlink()

    response = client.get(f"{CERT_URL}/{cert['certificate_id']}")

    assert response.status_code == 404
    assert str(output_dir) not in response.text
    assert list_certs(client, job_id)[0]["file_available"] is False


def test_download_all_successful_certificates_as_zip(client_factory):
    client = client_factory(FailingRenderer(fail_for={"Bob"}))
    job_id = create_job(client, "Alice", "Bob", "Carol")

    response = client.get(f"{JOBS_URL}/{job_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 2                      # Bob's failed certificate is not included
        assert all(name.endswith(".pdf") for name in names)
        assert archive.read(names[0]).startswith(b"%PDF")


def test_zip_with_no_successful_certificates_returns_409(client_factory):
    client = client_factory(FailingRenderer(fail_for={"Bob"}))
    job_id = create_job(client, "Bob")

    assert client.get(f"{JOBS_URL}/{job_id}/download").status_code == 409


def test_zip_for_unknown_job_returns_404(client):
    assert client.get(f"{JOBS_URL}/9999/download").status_code == 404
