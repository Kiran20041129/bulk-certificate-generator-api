"""Small helpers shared by the tests."""
from app.core.config import get_settings
from app.core.exceptions import CertificateGenerationError
from app.services.pdf_service import CertificateRenderer


def make_payload(*names: str, event_name: str = "AI Workshop 2026") -> dict:
    """Build a request body with one recipient per name."""
    return {
        "event_name": event_name,
        "date": "2026-10-07",
        "recipients": [
            {"name": name, "email": f"user{i}@example.com"} for i, name in enumerate(names)
        ],
    }


class FailingRenderer(CertificateRenderer):
    """Real renderer that raises a generation error for chosen names."""

    def __init__(self, fail_for: set[str]) -> None:
        super().__init__(get_settings().template_path)
        self.fail_for = fail_for

    def render(self, data, output_path):
        if data.recipient_name in self.fail_for:
            raise CertificateGenerationError("Simulated PDF failure")
        return super().render(data, output_path)


class CrashingRenderer(CertificateRenderer):
    """Raises an unexpected (non-domain) exception for chosen names."""

    def __init__(self, crash_for: set[str]) -> None:
        super().__init__(get_settings().template_path)
        self.crash_for = crash_for

    def render(self, data, output_path):
        if data.recipient_name in self.crash_for:
            raise RuntimeError("secret internal detail: /var/db/password")
        return super().render(data, output_path)
