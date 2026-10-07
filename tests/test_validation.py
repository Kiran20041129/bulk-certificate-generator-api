import pytest

from app.core.config import get_settings
from app.core.exceptions import RecipientValidationError
from app.services.recipient_validation import validate_recipient
from tests.helpers import make_payload

JOBS_URL = "/api/v1/certificates/jobs"


# ---- Request-level validation: the whole request is rejected with 422 ----
def test_empty_recipient_list_is_rejected(client):
    payload = make_payload()
    assert client.post(JOBS_URL, json=payload).status_code == 422


def test_missing_recipients_field_is_rejected(client):
    assert client.post(JOBS_URL, json={"event_name": "X", "date": "2026-10-07"}).status_code == 422


@pytest.mark.parametrize("event_name", ["", "   "])
def test_blank_event_name_is_rejected(client, event_name):
    response = client.post(JOBS_URL, json=make_payload("Alice", event_name=event_name))
    assert response.status_code == 422


def test_event_name_with_unprintable_characters_is_rejected(client):
    response = client.post(JOBS_URL, json=make_payload("Alice", event_name="राहुल Workshop"))
    assert response.status_code == 422


@pytest.mark.parametrize("bad_date", ["07-10-2026", "not-a-date", "2026-13-40", ""])
def test_invalid_date_is_rejected(client, bad_date):
    payload = make_payload("Alice")
    payload["date"] = bad_date
    assert client.post(JOBS_URL, json=payload).status_code == 422


def test_too_many_recipients_is_rejected(client):
    too_many = get_settings().max_recipients + 1
    payload = {"event_name": "X", "date": "2026-10-07", "recipients": [{"name": "A"}] * too_many}
    assert client.post(JOBS_URL, json=payload).status_code == 422


def test_recipient_with_wrong_type_is_rejected(client):
    payload = make_payload("Alice")
    payload["recipients"][0]["name"] = 12345
    assert client.post(JOBS_URL, json=payload).status_code == 422


# ---- Recipient-level validation: request accepted, bad recipient recorded as failed ----
def test_invalid_recipients_do_not_reject_the_request(client):
    payload = make_payload("Alice")
    payload["recipients"] += [
        {"name": "   ", "email": "blank@example.com"},     # blank name
        {"name": "Dave", "email": "not-an-email"},         # bad email
        {"name": "Erin"},                                  # no email: allowed
    ]

    response = client.post(JOBS_URL, json=payload)
    assert response.status_code == 202

    status = client.get(f"{JOBS_URL}/{response.json()['job_id']}").json()
    assert status["status"] == "completed_with_errors"
    assert status["total"] == 4
    assert status["successful"] == 2   # Alice, Erin
    assert status["failed"] == 2       # blank name, bad email
    errors = " ".join(f["error"] for f in status["failures"])
    assert "must not be blank" in errors
    assert "not a valid email" in errors


def test_missing_name_key_is_recorded_as_failure_not_dropped(client):
    payload = make_payload("Alice")
    payload["recipients"].append({"email": "noname@example.com"})

    job_id = client.post(JOBS_URL, json=payload).json()["job_id"]
    status = client.get(f"{JOBS_URL}/{job_id}").json()

    assert status["total"] == 2          # nobody silently disappears
    assert status["failed"] == 1


# ---- The validation function itself ----
def test_validate_recipient_accepts_good_data_and_trims_spaces():
    recipient = validate_recipient("  Kiran Naidu ", " kiran@example.com ")
    assert recipient.name == "Kiran Naidu"
    assert recipient.email == "kiran@example.com"


def test_validate_recipient_email_is_optional():
    assert validate_recipient("Kiran", None).email is None
    assert validate_recipient("Kiran", "  ").email is None


@pytest.mark.parametrize(
    "name, email, expected_message",
    [
        ("", None, "must not be blank"),
        (None, None, "must not be blank"),
        ("   ", None, "must not be blank"),
        ("A" * 81, None, "at most 80"),
        ("Line\nBreak", None, "invalid characters"),
        ("Kiran", "kiran.example.com", "not a valid email"),
        ("Kiran", "kiran@", "not a valid email"),
    ],
)
def test_validate_recipient_rejects_bad_data(name, email, expected_message):
    with pytest.raises(RecipientValidationError) as error:
        validate_recipient(name, email)
    assert expected_message in str(error.value)
