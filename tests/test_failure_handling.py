"""The most important behaviour: one bad certificate never stops the job."""
import pytest

from tests.helpers import CrashingRenderer, FailingRenderer, make_payload

JOBS_URL = "/api/v1/certificates/jobs"


def test_a_succeeds_b_fails_c_succeeds_and_the_job_continues(client_factory, output_dir):
    client = client_factory(FailingRenderer(fail_for={"Bob"}))

    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob", "Carol")).json()["job_id"]

    # The job ran to the end and says it had errors
    status = client.get(f"{JOBS_URL}/{job_id}").json()
    assert status["status"] == "completed_with_errors"
    assert (status["total"], status["completed"]) == (3, 3)
    assert (status["successful"], status["failed"]) == (2, 1)
    assert status["progress"] == 100

    # Alice and Carol (the recipient AFTER the failure) both have certificates
    certs = client.get(f"{JOBS_URL}/{job_id}/certificates").json()["certificates"]
    by_name = {c["recipient_name"]: c for c in certs}
    assert by_name["Alice"]["status"] == "success" and by_name["Alice"]["file_available"]
    assert by_name["Carol"]["status"] == "success" and by_name["Carol"]["file_available"]

    # Bob is recorded as failed, with the reason and no file
    assert by_name["Bob"]["status"] == "failed"
    assert by_name["Bob"]["file_available"] is False
    assert by_name["Bob"]["error_message"] == "Simulated PDF failure"
    assert [f["recipient_name"] for f in status["failures"]] == ["Bob"]
    assert len(list((output_dir / f"job_{job_id}").glob("*.pdf"))) == 2


@pytest.mark.parametrize("failing_position", range(7))
def test_failure_at_any_position_in_a_list_of_seven(client_factory, failing_position):
    names = [f"Person {i}" for i in range(7)]
    client = client_factory(FailingRenderer(fail_for={names[failing_position]}))

    job_id = client.post(JOBS_URL, json=make_payload(*names)).json()["job_id"]
    certs = client.get(f"{JOBS_URL}/{job_id}/certificates").json()["certificates"]

    statuses = [c["status"] for c in certs]
    expected = ["success"] * 7
    expected[failing_position] = "failed"
    assert statuses == expected


def test_unexpected_crash_is_contained_and_not_leaked_to_the_client(client_factory):
    client = client_factory(CrashingRenderer(crash_for={"Bob"}))

    job_id = client.post(JOBS_URL, json=make_payload("Alice", "Bob", "Carol")).json()["job_id"]
    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert status["status"] == "completed_with_errors"
    assert status["successful"] == 2
    error = status["failures"][0]["error"]
    assert "secret internal detail" not in error   # internals stay in the server log
    assert "Unexpected error" in error


def test_real_renderer_failure_for_unsupported_characters(client):
    """No simulation: a Devanagari name genuinely cannot be printed."""
    job_id = client.post(JOBS_URL, json=make_payload("Alice", "राहुल", "Carol")).json()["job_id"]
    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert status["status"] == "completed_with_errors"
    assert (status["successful"], status["failed"]) == (2, 1)
    assert "cannot print" in status["failures"][0]["error"]


def test_mixed_validation_and_generation_failures(client_factory):
    client = client_factory(FailingRenderer(fail_for={"Bob"}))
    payload = make_payload("Alice", "Bob", "Carol")
    payload["recipients"].insert(1, {"name": "", "email": "x@example.com"})  # invalid recipient

    job_id = client.post(JOBS_URL, json=payload).json()["job_id"]
    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert (status["total"], status["successful"], status["failed"]) == (4, 2, 2)
