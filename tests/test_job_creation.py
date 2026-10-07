from tests.helpers import make_payload

JOBS_URL = "/api/v1/certificates/jobs"


def test_create_job_returns_job_id_status_and_total(client):
    response = client.post(JOBS_URL, json=make_payload("Alice", "Bob"))

    assert response.status_code == 202
    body = response.json()
    assert isinstance(body["job_id"], int)
    assert body["status"] == "queued"
    assert body["total"] == 2


def test_each_recipient_gets_a_certificate_record(client):
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob", "Carol")).json()["job_id"]

    listing = client.get(f"{JOBS_URL}/{job_id}/certificates").json()

    assert listing["total"] == 3
    assert [c["recipient_name"] for c in listing["certificates"]] == ["Alice", "Bob", "Carol"]


def test_job_is_processed_in_the_background_after_creation(client):
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob")).json()["job_id"]

    # TestClient runs background tasks before returning, so the job is finished.
    status = client.get(f"{JOBS_URL}/{job_id}").json()
    assert status["status"] == "completed"


def test_many_recipients_in_one_request(client):
    names = [f"Person {i}" for i in range(25)]
    job_id = client.post(JOBS_URL, json=make_payload(*names)).json()["job_id"]

    status = client.get(f"{JOBS_URL}/{job_id}").json()
    assert status["total"] == 25
    assert status["successful"] == 25


def test_unknown_job_returns_404(client):
    response = client.get(f"{JOBS_URL}/9999")
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]
