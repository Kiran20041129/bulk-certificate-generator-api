"""Per-recipient validation (uses the strict Pydantic model)."""
from pydantic import ValidationError

from app.core.exceptions import RecipientValidationError
from app.schemas.certificate import RecipientValidated


def validate_recipient(name: str | None, email: str | None) -> RecipientValidated:
    """Return the cleaned recipient, or raise RecipientValidationError."""
    try:
        return RecipientValidated(name=name or "", email=email)
    except ValidationError as exc:
        messages = [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
        raise RecipientValidationError("; ".join(messages)) from exc
