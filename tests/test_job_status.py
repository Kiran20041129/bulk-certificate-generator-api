from sqlalchemy import select

from app.db.models import GenerationJob
from app.services.certificate_service import calculate_progress
from app.services.generation_service import decide_final_status
from app.services.pdf_service import CertificateRenderer
from tests.helpers import make_payload

JOBS_URL = "/api/v1/certificates/jobs"


def test_completed_job_reports_full_progress(client):
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob", "Carol")).json()["job_id"]

    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert status["status"] == "completed"
    assert (status["total"], status["completed"]) == (3, 3)
    assert (status["successful"], status["failed"]) == (3, 0)
    assert status["progress"] == 100
    assert status["failures"] == []
    assert status["created_at"] and status["started_at"] and status["completed_at"]


def test_job_where_everything_fails_is_marked_failed(client_factory, tmp_path):
    missing_template = CertificateRenderer(tmp_path / "no_template.pdf")
    client = client_factory(missing_template)

    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob")).json()["job_id"]
    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert status["status"] == "failed"
    assert status["failed"] == 2 and status["successful"] == 0
    assert status["progress"] == 100  # every certificate was attempted
    assert "template is missing" in status["failures"][0]["error"]


def test_progress_is_visible_while_the_job_is_processing(client_factory, session_factory, real_renderer):
    """Peek at the database from inside the renderer, i.e. while the job runs."""
    snapshots = []

    class ProbeRenderer(CertificateRenderer):
        def render(self, data, output_path):
            with session_factory() as db:
                job = db.scalars(select(GenerationJob)).one()
                snapshots.append((job.status, job.completed_count))
            return real_renderer.render(data, output_path)

    client = client_factory(ProbeRenderer(real_renderer.template_path))
    client.post(JOBS_URL, json=make_payload("A", "B", "C"))

    assert snapshots == [("processing", 0), ("processing", 1), ("processing", 2)]


def test_calculate_progress():
    assert calculate_progress(0, 10) == 0
    assert calculate_progress(5, 10) == 50
    assert calculate_progress(1, 3) == 33
    assert calculate_progress(10, 10) == 100
    assert calculate_progress(0, 0) == 0  # no division by zero


def test_final_status_rules():
    assert decide_final_status(total=5, successful=5) == "completed"
    assert decide_final_status(total=5, successful=3) == "completed_with_errors"
    assert decide_final_status(total=5, successful=0) == "failed"
