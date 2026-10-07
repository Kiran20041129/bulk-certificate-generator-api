"""Database operations for jobs and certificates (no PDF work, no HTTP)."""
import io
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    CertificateFileMissingError,
    CertificateNotFoundError,
    CertificateNotReadyError,
    JobNotFoundError,
    NoCertificatesAvailableError,
)
from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.schemas.certificate import (
    CertificateOut,
    FailureOut,
    JobCreateRequest,
    JobStatusOut,
)
from app.utils.file_utils import safe_filename


def generate_certificate_code() -> str:
    """Short unique ID printed on the certificate, e.g. CERT-3F9A1C7B2E."""
    return f"CERT-{uuid.uuid4().hex[:10].upper()}"


def calculate_progress(completed: int, total: int) -> int:
    """Percentage of certificates finished (success or failed)."""
    return 0 if total == 0 else completed * 100 // total


def create_job(db: Session, payload: JobCreateRequest) -> GenerationJob:
    """Save the job and one 'pending' certificate row per recipient."""
    job = GenerationJob(
        event_name=payload.event_name,
        event_date=payload.date,
        status=JobStatus.QUEUED.value,
        total_count=len(payload.recipients),
        completed_count=0,
        successful_count=0,
        failed_count=0,
    )
    job.certificates = [
        Certificate(
            certificate_code=generate_certificate_code(),
            recipient_name=recipient.name or "",
            recipient_email=recipient.email,
            status=CertificateStatus.PENDING.value,
        )
        for recipient in payload.recipients
    ]
    db.add(job)
    db.commit()
    return job


def get_job(db: Session, job_id: int) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    return job


def get_certificate(db: Session, certificate_id: int) -> Certificate:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise CertificateNotFoundError(certificate_id)
    return certificate


def build_job_status(db: Session, job: GenerationJob) -> JobStatusOut:
    failed_rows = db.scalars(
        select(Certificate)
        .where(
            Certificate.job_id == job.id,
            Certificate.status == CertificateStatus.FAILED.value,
        )
        .order_by(Certificate.id)
    ).all()
    return JobStatusOut(
        job_id=job.id,
        event_name=job.event_name,
        status=job.status,
        total=job.total_count,
        completed=job.completed_count,
        successful=job.successful_count,
        failed=job.failed_count,
        progress=calculate_progress(job.completed_count, job.total_count),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        failures=[
            FailureOut(
                certificate_id=row.id,
                recipient_name=row.recipient_name,
                error=row.error_message,
            )
            for row in failed_rows
        ],
    )


def to_certificate_out(certificate: Certificate) -> CertificateOut:
    file_available = (
        certificate.status == CertificateStatus.SUCCESS.value
        and certificate.file_path is not None
        and Path(certificate.file_path).is_file()
    )
    return CertificateOut(
        certificate_id=certificate.id,
        certificate_code=certificate.certificate_code,
        recipient_name=certificate.recipient_name,
        recipient_email=certificate.recipient_email,
        status=certificate.status,
        file_available=file_available,
        download_url=f"/api/v1/certificates/{certificate.id}" if file_available else None,
        error_message=certificate.error_message,
    )


def list_certificates(
    db: Session, job_id: int, limit: int, offset: int
) -> tuple[int, list[Certificate]]:
    """Return (total in job, one page of certificates)."""
    get_job(db, job_id)  # raises JobNotFoundError for unknown jobs
    total = db.scalar(
        select(func.count()).select_from(Certificate).where(Certificate.job_id == job_id)
    )
    rows = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id)
        .order_by(Certificate.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return total or 0, list(rows)


def get_downloadable_file(db: Session, certificate_id: int) -> tuple[Path, str]:
    """Return (path on disk, download file name) or raise a clear error."""
    certificate = get_certificate(db, certificate_id)
    if certificate.status != CertificateStatus.SUCCESS.value or not certificate.file_path:
        raise CertificateNotReadyError(
            f"Certificate {certificate_id} has no PDF (status: {certificate.status})."
        )
    path = Path(certificate.file_path)
    if not path.is_file():
        raise CertificateFileMissingError(
            f"The PDF for certificate {certificate_id} is missing from storage."
        )
    return path, _download_name(certificate)


def build_job_zip(db: Session, job_id: int) -> bytes:
    """Bundle every successful certificate of a job into one ZIP (in memory)."""
    get_job(db, job_id)
    certificates = db.scalars(
        select(Certificate)
        .where(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.SUCCESS.value,
        )
        .order_by(Certificate.id)
    ).all()

    buffer = io.BytesIO()
    added = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for certificate in certificates:
            if certificate.file_path and Path(certificate.file_path).is_file():
                archive.write(certificate.file_path, arcname=_download_name(certificate))
                added += 1
    if added == 0:
        raise NoCertificatesAvailableError(
            f"Job {job_id} has no generated certificates to download."
        )
    return buffer.getvalue()


def _download_name(certificate: Certificate) -> str:
    """File name shown to the user. Built from safe text, never raw input."""
    return f"{safe_filename(certificate.recipient_name)}_{certificate.certificate_code}.pdf"
