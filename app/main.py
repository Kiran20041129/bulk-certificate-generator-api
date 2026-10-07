"""Application entry point: creates the FastAPI app and wires everything up."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import certificate_routes
from app.core.config import get_settings
from app.core.exceptions import (
    CertificateFileMissingError,
    CertificateNotFoundError,
    CertificateNotReadyError,
    JobNotFoundError,
    NoCertificatesAvailableError,
)
from app.db.database import Base, engine

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Which expected errors become which HTTP status codes.
ERROR_STATUS_CODES = {
    JobNotFoundError: 404,
    CertificateNotFoundError: 404,
    CertificateFileMissingError: 404,
    CertificateNotReadyError: 409,
    NoCertificatesAvailableError: 409,
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # create tables on first start
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    if not settings.template_path.is_file():
        logger.warning("Template not found at %s; run scripts/create_template.py", settings.template_path)
    yield


app = FastAPI(
    title="Bulk Certificate Generator API",
    description=(
        "Submit a list of recipients, get a job ID, track progress, and download "
        "the generated PDF certificates. A failure for one recipient never stops the others."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(certificate_routes.router)
@app.get("/")
def home():
    return {
        "message": "Bulk Certificate Generator API is running",
        "status": "success"
    }


async def handle_known_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=ERROR_STATUS_CODES[type(exc)], content={"detail": str(exc)})


for error_class in ERROR_STATUS_CODES:
    app.add_exception_handler(error_class, handle_known_error)


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)  # details stay in the server log
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", tags=["Health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
