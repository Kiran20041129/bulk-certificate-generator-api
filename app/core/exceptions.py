"""Domain exceptions. The API layer turns these into HTTP responses."""


class CertificateAppError(Exception):
    """Base class for all expected application errors."""


# --- raised while processing a single certificate (recorded, never fatal) ---
class RecipientValidationError(CertificateAppError):
    """The recipient's data is not valid (blank name, bad email, ...)."""


class TemplateNotFoundError(CertificateAppError):
    """The certificate template PDF is missing."""


class CertificateGenerationError(CertificateAppError):
    """The PDF could not be produced for this recipient."""


# --- raised by the API layer (mapped to 404 / 409) ---
class JobNotFoundError(CertificateAppError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"Job {job_id} was not found.")


class CertificateNotFoundError(CertificateAppError):
    def __init__(self, certificate_id: int) -> None:
        super().__init__(f"Certificate {certificate_id} was not found.")


class CertificateNotReadyError(CertificateAppError):
    """The certificate exists but has no PDF (still pending, or failed)."""


class CertificateFileMissingError(CertificateAppError):
    """The database says a PDF exists but the file is gone from disk."""


class NoCertificatesAvailableError(CertificateAppError):
    """A job has no successfully generated certificates to download."""
