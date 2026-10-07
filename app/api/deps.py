"""FastAPI dependencies. Tests replace these with test versions."""
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.services.generation_service import GenerationService
from app.services.pdf_service import CertificateRenderer


def get_db() -> Iterator[Session]:
    """One database session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_generation_service() -> GenerationService:
    settings = get_settings()
    return GenerationService(
        session_factory=SessionLocal,
        renderer=CertificateRenderer(settings.template_path),
        output_dir=settings.output_dir,
    )
