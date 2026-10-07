"""Pydantic models: what the API accepts and returns."""
import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.utils.text_utils import is_pdf_safe

MAX_NAME_LENGTH = 80
MAX_EVENT_LENGTH = 100
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------- request models -------------------------------
class RecipientIn(BaseModel):
    """A recipient as submitted.

    Deliberately lenient: only the *types* are checked here. Business rules
    (blank name, bad email) are checked per recipient later, so one bad
    recipient becomes a recorded failure instead of rejecting the whole job.
    """

    name: str | None = Field(default="", description="Name printed on the certificate.")
    email: str | None = Field(default=None, description="Optional email address.")


class JobCreateRequest(BaseModel):
    """Body of POST /api/v1/certificates/jobs."""

    event_name: str = Field(description="Event or course name printed on every certificate.")
    date: dt.date = Field(description="Event date, format YYYY-MM-DD.")
    recipients: list[RecipientIn] = Field(
        min_length=1,
        max_length=get_settings().max_recipients,
        description="One or more recipients.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_name": "AI Workshop 2026",
                "date": "2026-10-07",
                "recipients": [
                    {"name": "Kiran Naidu", "email": "kiran@example.com"},
                    {"name": "Rahul Kumar", "email": "rahul@example.com"},
                ],
            }
        }
    )

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("event_name must not be blank")
        if len(value) > MAX_EVENT_LENGTH:
            raise ValueError(f"event_name must be at most {MAX_EVENT_LENGTH} characters")
        if not value.isprintable():
            raise ValueError("event_name contains invalid characters")
        if not is_pdf_safe(value):
            raise ValueError("event_name may only contain Latin characters")
        return value


class RecipientValidated(BaseModel):
    """Strict per-recipient rules, applied during processing."""

    name: str
    email: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Recipient name must not be blank")
        if len(value) > MAX_NAME_LENGTH:
            raise ValueError(f"Recipient name must be at most {MAX_NAME_LENGTH} characters")
        if not value.isprintable():
            raise ValueError("Recipient name contains invalid characters")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not EMAIL_PATTERN.match(value) or len(value) > 320:
            raise ValueError(f"'{value}' is not a valid email address")
        return value


# ----------------------------- response models -------------------------------
class JobCreatedOut(BaseModel):
    job_id: int
    status: str
    total: int


class FailureOut(BaseModel):
    certificate_id: int
    recipient_name: str
    error: str | None


class JobStatusOut(BaseModel):
    job_id: int
    event_name: str
    status: str
    total: int
    completed: int = Field(description="Certificates finished so far (success + failed).")
    successful: int
    failed: int
    progress: int = Field(description="Percentage 0-100: completed / total.")
    created_at: dt.datetime
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    error_message: str | None = Field(description="Set only if the whole job crashed.")
    failures: list[FailureOut]


class CertificateOut(BaseModel):
    certificate_id: int
    certificate_code: str
    recipient_name: str
    recipient_email: str | None
    status: str
    file_available: bool
    download_url: str | None
    error_message: str | None


class CertificateListOut(BaseModel):
    job_id: int
    total: int
    limit: int
    offset: int
    certificates: list[CertificateOut]


class ErrorOut(BaseModel):
    detail: str
