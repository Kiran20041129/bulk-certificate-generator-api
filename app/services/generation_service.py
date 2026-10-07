"""Runs a bulk job in the background, one certificate at a time.

The rule that matters most: a problem with ONE recipient is caught, recorded
on that recipient's row, and the loop moves on to the next recipient.
"""
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import (
    CertificateGenerationError,
    RecipientValidationError,
    TemplateNotFoundError,
)
from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus, utcnow
from app.services.pdf_service import CertificateData, CertificateRenderer
from app.services.recipient_validation import validate_recipient

logger = logging.getLogger(__name__)
GENERIC_ERROR = "Unexpected error while generating this certificate."


def decide_final_status(total: int, successful: int) -> str:
    """Pick the job's final status from its results."""
    if successful == 0:
        return JobStatus.FAILED.value
    if successful == total:
        return JobStatus.COMPLETED.value
    return JobStatus.COMPLETED_WITH_ERRORS.value


class GenerationService:
    """Processes jobs. Gets its own DB sessions because it runs after the
    HTTP request has finished (the request's session is already closed)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        renderer: CertificateRenderer,
        output_dir: Path,
    ) -> None:
        self.session_factory = session_factory
        self.renderer = renderer
        self.output_dir = Path(output_dir)

    def process_job(self, job_id: int) -> None:
        """Entry point used by FastAPI's BackgroundTasks. Never raises."""
        try:
            self._run(job_id)
        except Exception:
            logger.exception("Job %s crashed unexpectedly", job_id)
            self._mark_job_crashed(job_id)

    # ------------------------------------------------------------------ steps
    def _run(self, job_id: int) -> None:
        with self.session_factory() as db:
            job = db.get(GenerationJob, job_id)
            if job is None:
                logger.error("Job %s does not exist; nothing to process", job_id)
                return
            job.status = JobStatus.PROCESSING.value  # queued -> processing
            job.started_at = utcnow()
            db.commit()
            event_name, event_date = job.event_name, job.event_date
            certificate_ids = list(
                db.scalars(
                    select(Certificate.id)
                    .where(Certificate.job_id == job_id)
                    .order_by(Certificate.id)
                )
            )

        logger.info("Job %s started: %d certificates", job_id, len(certificate_ids))
        for certificate_id in certificate_ids:
            try:
                self._process_certificate(job_id, certificate_id, event_name, event_date)
            except Exception:  # even a DB hiccup must not stop the other recipients
                logger.exception("Certificate %s: could not save its result", certificate_id)

        self._finalize_job(job_id)

    def _process_certificate(
        self, job_id: int, certificate_id: int, event_name: str, event_date: date
    ) -> None:
        """Handle ONE recipient in its own session/transaction."""
        with self.session_factory() as db:
            certificate = db.get(Certificate, certificate_id)
            job = db.get(GenerationJob, job_id)
            try:
                recipient = validate_recipient(certificate.recipient_name, certificate.recipient_email)
                data = CertificateData(
                    recipient_name=recipient.name,
                    event_name=event_name,
                    event_date=event_date,
                    certificate_code=certificate.certificate_code,
                )
                path = self.renderer.render(data, self._output_path(job_id, certificate))
            except (RecipientValidationError, CertificateGenerationError) as exc:
                logger.warning("Certificate %s failed: %s", certificate_id, exc)
                self._record_failure(certificate, job, str(exc))
            except TemplateNotFoundError as exc:
                logger.error("Certificate %s failed: %s", certificate_id, exc)
                self._record_failure(certificate, job, str(exc))
            except Exception:
                # Unknown bug: log the details for us, show a generic message to clients.
                logger.exception("Certificate %s failed unexpectedly", certificate_id)
                self._record_failure(certificate, job, GENERIC_ERROR)
            else:
                certificate.status = CertificateStatus.SUCCESS.value
                certificate.file_path = str(path)
                certificate.generated_at = utcnow()
                job.successful_count += 1
            job.completed_count += 1
            db.commit()  # commit per certificate => progress is visible immediately

    def _finalize_job(self, job_id: int) -> None:
        """Recount from the certificate rows (the source of truth) and close the job."""
        with self.session_factory() as db:
            job = db.get(GenerationJob, job_id)
            rows = db.execute(
                select(Certificate.status, func.count())
                .where(Certificate.job_id == job_id)
                .group_by(Certificate.status)
            ).all()
            counts = {status: count for status, count in rows}
            job.successful_count = counts.get(CertificateStatus.SUCCESS.value, 0)
            job.failed_count = counts.get(CertificateStatus.FAILED.value, 0)
            job.completed_count = job.successful_count + job.failed_count
            job.status = decide_final_status(job.total_count, job.successful_count)
            job.completed_at = utcnow()
            db.commit()
            logger.info(
                "Job %s finished: %s (%d ok, %d failed)",
                job_id, job.status, job.successful_count, job.failed_count,
            )

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _record_failure(certificate: Certificate, job: GenerationJob, message: str) -> None:
        certificate.status = CertificateStatus.FAILED.value
        certificate.error_message = message[:500]
        job.failed_count += 1

    def _output_path(self, job_id: int, certificate: Certificate) -> Path:
        # File name uses the generated code, never the recipient's name,
        # so user input can never decide where a file is written.
        return self.output_dir / f"job_{job_id}" / f"{certificate.certificate_code}.pdf"

    def _mark_job_crashed(self, job_id: int) -> None:
        try:
            with self.session_factory() as db:
                job = db.get(GenerationJob, job_id)
                if job is not None:
                    job.status = JobStatus.FAILED.value
                    job.error_message = "The job stopped because of an internal error."
                    job.completed_at = utcnow()
                    db.commit()
        except Exception:
            logger.exception("Could not mark job %s as failed", job_id)
