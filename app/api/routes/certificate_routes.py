"""HTTP endpoints. Thin on purpose: logic lives in the services."""
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_generation_service
from app.schemas.certificate import (
    CertificateListOut,
    ErrorOut,
    JobCreatedOut,
    JobCreateRequest,
    JobStatusOut,
)
from app.services import certificate_service
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/api/v1/certificates", tags=["Certificates"])

NOT_FOUND = {404: {"model": ErrorOut, "description": "Resource not found"}}


@router.post(
    "/jobs",
    response_model=JobCreatedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a bulk certificate job",
    description=(
        "Accepts many recipients in one request, saves them, and returns immediately "
        "with a job ID. Certificates are generated in the background; poll the job "
        "status endpoint to follow progress. Recipients with invalid data do not "
        "reject the request: they are recorded as failed certificates."
    ),
    responses={422: {"description": "Invalid request body (e.g. empty recipients, bad date)"}},
)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    generation_service: GenerationService = Depends(get_generation_service),
) -> JobCreatedOut:
    job = certificate_service.create_job(db, payload)
    background_tasks.add_task(generation_service.process_job, job.id)
    return JobCreatedOut(job_id=job.id, status=job.status, total=job.total_count)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusOut,
    summary="Get job status and progress",
    description="Returns status, counters, progress percentage and the list of failures.",
    responses=NOT_FOUND,
)
def get_job_status(job_id: int, db: Session = Depends(get_db)) -> JobStatusOut:
    job = certificate_service.get_job(db, job_id)
    return certificate_service.build_job_status(db, job)


@router.get(
    "/jobs/{job_id}/certificates",
    response_model=CertificateListOut,
    summary="List the certificates of a job",
    description="One entry per recipient with its status, error (if failed) and download link.",
    responses=NOT_FOUND,
)
def list_job_certificates(
    job_id: int,
    limit: int = Query(100, ge=1, le=1000, description="Page size."),
    offset: int = Query(0, ge=0, description="How many certificates to skip."),
    db: Session = Depends(get_db),
) -> CertificateListOut:
    total, certificates = certificate_service.list_certificates(db, job_id, limit, offset)
    return CertificateListOut(
        job_id=job_id,
        total=total,
        limit=limit,
        offset=offset,
        certificates=[certificate_service.to_certificate_out(c) for c in certificates],
    )


@router.get(
    "/jobs/{job_id}/download",
    summary="Download all successful certificates as a ZIP",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "ZIP archive of PDFs"},
        **NOT_FOUND,
        409: {"model": ErrorOut, "description": "No generated certificates yet"},
    },
)
def download_job_zip(job_id: int, db: Session = Depends(get_db)) -> Response:
    archive = certificate_service.build_job_zip(db, job_id)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_certificates.zip"'},
    )


@router.get(
    "/{certificate_id}",
    response_class=FileResponse,
    summary="Download one certificate (PDF)",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The certificate PDF"},
        **NOT_FOUND,
        409: {"model": ErrorOut, "description": "Certificate has no PDF (pending or failed)"},
    },
)
def download_certificate(certificate_id: int, db: Session = Depends(get_db)) -> FileResponse:
    path, filename = certificate_service.get_downloadable_file(db, certificate_id)
    return FileResponse(path, media_type="application/pdf", filename=filename)
