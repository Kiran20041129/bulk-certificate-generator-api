# Requirements compliance checklist

**Verification legend**
- **RUN** = I actually executed it in the build environment and inspected the result.
- **WRITTEN** = code and tests are written and syntax-checked, but could **not** be executed
  in the build environment (it had no network, so FastAPI, SQLAlchemy, Pydantic and pytest
  could not be installed). Run `pytest` on your machine to complete verification.

## Assignment requirements

| # | Requirement (from the assignment) | Implementation | Test | Status |
|---|---|---|---|---|
| 1 | Accept a certificate generation request | `POST /api/v1/certificates/jobs` -> `certificate_routes.create_job` | `test_job_creation.py::test_create_job_returns_job_id_status_and_total` | WRITTEN |
| 2 | Bulk: many recipients in one request | `recipients: list[RecipientIn]` (1..1000) | `test_many_recipients_in_one_request` | WRITTEN |
| 3 | Validate recipient data | `RecipientValidated` + `recipient_validation.py`; request-level rules in `JobCreateRequest` | `test_validation.py` (14 cases) | WRITTEN |
| 4 | Single predefined template | `templates/certificate_template.pdf` (made by `scripts/create_template.py`) | `test_renderer_keeps_template_text` | **RUN** (template generated and viewed) |
| 5 | Recipient-specific info on each certificate | `pdf_service.CertificateRenderer` overlays name/event/date/ID | `test_renderer_creates_a_pdf_with_the_recipient_details` | **RUN** (text extracted from the PDF and checked manually) |
| 6 | Track generation status | `GenerationJob.status` with 5 states | `test_job_status.py` | WRITTEN |
| 7 | Check progress/result | `GET /jobs/{id}` -> counters, `progress`, `failures` | `test_completed_job_reports_full_progress`, `test_progress_is_visible_while_the_job_is_processing` | WRITTEN |
| 8 | Retrieve generated certificates | `GET /certificates/{id}` (PDF), `/jobs/{id}/certificates`, `/jobs/{id}/download` (ZIP) | `test_retrieval.py` (10 tests) | WRITTEN |
| 9 | One failure must not stop others | per-certificate try/except + own transaction in `generation_service._process_certificate` | `test_failure_handling.py::test_a_succeeds_b_fails_c_succeeds_and_the_job_continues` (+ 7-position test) | WRITTEN |
| 10 | Status identifies successes and failures | per-certificate `status` + `error_message`; job `failures` list | same as #9, `test_mixed_validation_and_generation_failures` | WRITTEN |
| 11 | Relational database | SQLAlchemy models, SQLite, FK `certificates.job_id -> generation_jobs.id` | all API tests use a real SQLite file | WRITTEN |
| 12 | Document bulk-processing choice and reasoning | README -> *Design decisions* | n/a | DONE (document) |
| 13 | Tests: job creation, validation, generation, status, failure, retrieval | six test files, one per area | `pytest` | WRITTEN |
| 14 | README: setup, run, test, submit request, retrieve, design decisions | `README.md` | n/a | DONE (document) |
| 15 | Easy to run locally | `pip install -r requirements.txt` + `uvicorn app.main:app --reload`; tables auto-created | n/a | WRITTEN |

## Failure handling cases

| Case | Behaviour | Status |
|---|---|---|
| Invalid body / empty recipients / bad date / too many | 422 | WRITTEN |
| Blank name / bad email | job created, recipient recorded as failed with reason | WRITTEN |
| Unprintable characters in name (e.g. Devanagari) | recorded as failed with reason | **RUN** (renderer raises the right error) / WRITTEN (through API) |
| Missing template | every certificate fails -> job `failed` | **RUN** (renderer) / WRITTEN (through API) |
| Unknown job / certificate | 404 | WRITTEN |
| Certificate not generated (failed/pending) | 409 | WRITTEN |
| PDF file deleted from disk | 404, no internal path leaked | WRITTEN |
| Unexpected exception | 500 / generic message, details logged only | WRITTEN |

## Not yet verified (be honest in the interview)

- `pytest` has not been executed (see legend).
- The server has not been started and Swagger UI has not been opened.
- No end-to-end run of the demo script.

Expect that a first run might expose small issues (typos, version differences). The
sections of code most worth reading if something fails: `tests/conftest.py` (dependency
overrides) and `app/services/generation_service.py`.
