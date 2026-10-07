# Bulk Certificate Generator API

A backend API that takes **one request containing many recipients**, generates a
PDF certificate for each of them from a predefined template, and lets the client
**track progress** and **download** the results. If one certificate fails, the
others are still generated and the failure is recorded with a reason.

Built for the *Bulk Certificate Generator* backend assignment.

## Features

- Bulk request: many recipients in a single `POST`
- Generation runs in the **background**; the API answers immediately with a job ID
- Job status + progress percentage + success/failure counters
- **Per-recipient failure isolation**: a failure is recorded, the job continues
- Pydantic validation (request-level and per-recipient)
- One predefined, professional PDF template (A4 landscape)
- Download one certificate (PDF) or all successful ones as a **ZIP**
- Unique **certificate ID** on every certificate (e.g. `CERT-3F9A1C7B2E`)
- Clear HTTP errors (404 / 409 / 422) with no stack traces leaked
- Automated tests with pytest; Swagger UI at `/docs`

## Tech stack

| Purpose | Tool |
|---|---|
| Web framework | FastAPI |
| Database | SQLite (local) via SQLAlchemy 2.0 - PostgreSQL-compatible |
| Validation / schemas | Pydantic v2 |
| PDF generation | ReportLab (draws text) + pypdf (merges onto the template) |
| Tests | pytest + FastAPI TestClient (httpx) |

## Project structure

```
app/
  main.py                      App creation, error handlers, startup
  api/deps.py                  Dependencies (DB session, generation service)
  api/routes/certificate_routes.py   The 5 endpoints (thin: no logic)
  core/config.py               Settings from environment / .env
  core/exceptions.py           Domain errors (mapped to HTTP codes in main.py)
  db/database.py               Engine + session factory
  db/models.py                 GenerationJob and Certificate tables, statuses
  schemas/certificate.py       Pydantic request/response models + validation rules
  services/certificate_service.py   DB operations (create job, list, zip, ...)
  services/generation_service.py    Background loop; per-certificate failure handling
  services/pdf_service.py           Template + overlay PDF rendering
  services/recipient_validation.py  Per-recipient validation
  utils/                       safe_filename, character check
templates/certificate_template.pdf  The single predefined template
scripts/create_template.py     Re-creates the template
scripts/demo.py                Runs the demo against a running server
sample_data/demo_request.json  6 recipients, 2 of them intentionally failing
tests/                         pytest suite
```

## Setup

Requires Python 3.10+.

```bash
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (cmd)
venv\Scripts\activate.bat
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

No other setup: the SQLite database and tables are created automatically on first start,
and the template PDF is already included.

## Run

```bash
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for Swagger UI.

(Optional settings: copy `.env.example` to `.env`.)

## API summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/certificates/jobs` | Create a bulk job (returns `202`) |
| GET | `/api/v1/certificates/jobs/{job_id}` | Status, progress, failures |
| GET | `/api/v1/certificates/jobs/{job_id}/certificates` | List certificates (`?limit=&offset=`) |
| GET | `/api/v1/certificates/jobs/{job_id}/download` | ZIP of all successful PDFs |
| GET | `/api/v1/certificates/{certificate_id}` | Download one PDF |
| GET | `/health` | Health check |

### Try it in Swagger UI

1. Open `/docs` -> **POST /api/v1/certificates/jobs** -> *Try it out*.
2. Paste the body from `sample_data/demo_request.json` -> *Execute*. Note the `job_id`.
3. Use **GET /jobs/{job_id}** with that ID to see progress and failures.
4. Use **GET /jobs/{job_id}/certificates** to find a `certificate_id`, then
   **GET /certificates/{certificate_id}** to download the PDF.

### Example request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/certificates/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "AI Workshop 2026",
    "date": "2026-10-07",
    "recipients": [
      {"name": "Kiran Naidu", "email": "kiran@example.com"},
      {"name": "Rahul Kumar", "email": "rahul@example.com"}
    ]
  }'
```

### Example response (`202 Accepted`)

```json
{ "job_id": 1, "status": "queued", "total": 2 }
```

### Checking status

```bash
curl http://127.0.0.1:8000/api/v1/certificates/jobs/1
```

```json
{
  "job_id": 1,
  "event_name": "AI Workshop 2026",
  "status": "completed_with_errors",
  "total": 6,
  "completed": 6,
  "successful": 4,
  "failed": 2,
  "progress": 100,
  "created_at": "2026-10-07T10:00:00.120000",
  "started_at": "2026-10-07T10:00:00.150000",
  "completed_at": "2026-10-07T10:00:00.480000",
  "error_message": null,
  "failures": [
    {"certificate_id": 3, "recipient_name": "Priya Sharma",
     "error": "'not-an-email' is not a valid email address"},
    {"certificate_id": 5, "recipient_name": "राहुल वर्मा",
     "error": "The recipient name contains characters the certificate font cannot print (only Latin characters are supported)."}
  ]
}
```

(The exact numbers above are illustrative; run the demo to see your own.)

### Retrieving certificates

```bash
# list them (shows status, error, download_url for each)
curl http://127.0.0.1:8000/api/v1/certificates/jobs/1/certificates

# one PDF
curl -o certificate.pdf http://127.0.0.1:8000/api/v1/certificates/1

# all successful PDFs in one ZIP
curl -o job_1.zip http://127.0.0.1:8000/api/v1/certificates/jobs/1/download
```

Generated files are stored in `generated/job_<id>/<certificate_code>.pdf`.

### Run the demo

With the server running in one terminal:

```bash
python scripts/demo.py
```

It submits 6 recipients (one invalid email, one name the PDF font cannot print), polls the
job, prints the failures, and saves the 4 good PDFs to `demo_output/`.

## Testing

```bash
pytest
```

Each test uses its own temporary SQLite database and output folder, so tests never touch
real data. Coverage by assignment requirement:

| Required area | Test file |
|---|---|
| Creating a generation job | `tests/test_job_creation.py` |
| Input validation | `tests/test_validation.py` |
| Certificate generation | `tests/test_generation.py` |
| Job status / progress | `tests/test_job_status.py` |
| Individual certificate failure | `tests/test_failure_handling.py` |
| Retrieving certificates | `tests/test_retrieval.py` |

The key test is `test_a_succeeds_b_fails_c_succeeds_and_the_job_continues`; a second test
makes the failure happen at each of 7 positions in a list.

## Status model

```
Job:          queued -> processing -> completed | completed_with_errors | failed
Certificate:  pending -> success | failed
```

- `completed`: every certificate succeeded
- `completed_with_errors`: at least one succeeded and at least one failed
- `failed`: nothing succeeded (e.g. the template file is missing)

## Design decisions

**Why FastAPI?** Request validation, error responses and Swagger docs come from the same
Pydantic models, so the API documents itself, which makes it easy to test and demo.

**Why background processing (not synchronous)?** A request may contain hundreds of
recipients. Generating them all before responding would hold the HTTP connection open and
risk client timeouts. Instead `POST` saves the job, schedules `GenerationService.process_job`
with FastAPI `BackgroundTasks`, and returns `202` with a job ID. The client polls the status
endpoint. I chose `BackgroundTasks` over Celery/Redis because it needs no extra
infrastructure; the trade-off is that a server restart during a job interrupts it (see
*Limitations*).

**Why a relational database?** The data is naturally related (a job has many certificates),
and we need consistent counters and filtered queries ("all failed certificates of job 7").

**Why two tables (job + certificate)?** The *job* holds shared information (event, date) and
overall progress. Each *certificate* holds one recipient's own status, file path and error.
That separation is what makes per-recipient failure tracking possible; one table could not
say "recipient 5 failed, the others succeeded" cleanly.

**Per-certificate failure handling.** The generation loop wraps every recipient in its own
`try/except` and its own database transaction. A validation or PDF error is saved on that
certificate (`status=failed`, `error_message=...`) and the loop continues. Unexpected bugs
are caught too: the full stack trace goes to the server log while the client only sees a
generic message. Because each certificate is committed separately, progress is visible while
the job runs. At the end the job recounts results from the certificate rows (the source of
truth) and sets its final status.

**Invalid recipients: reject the request, or record a failure?** Two kinds of problems are
treated differently:
- *Structural* problems (empty list, no `event_name`, invalid date, more than 1000
  recipients, wrong JSON types) mean the request itself is unusable -> **`422`**, nothing saved.
- *Recipient data* problems (blank name, bad email) -> the job is created and that
  recipient is recorded as a **failed certificate with the reason**. This follows the
  assignment ("a failure for one recipient should not prevent others") and means no
  recipient silently disappears.

**How text is placed on the certificate.** `templates/certificate_template.pdf` contains the
fixed design. For each recipient, ReportLab draws only the name, event, date and certificate ID
on a transparent page of the same size at fixed coordinates (constants at the top of
`pdf_service.py`), and pypdf merges it onto the template. Long names/events automatically
shrink to fit. Files are named after the generated certificate code, never the recipient's
name, so user input cannot influence file paths.

**Why SQLite locally?** Zero setup, one file, ideal for an assignment. SQLAlchemy keeps the
code database-neutral; switching to PostgreSQL means changing `DATABASE_URL` (plus installing
`psycopg2-binary`). SQLite is configured with `PRAGMA foreign_keys=ON` and WAL mode.

**Optional improvements I chose** (small, useful, easy to explain):
1. Unique certificate ID printed on every certificate.
2. ZIP download of all successful certificates in a job.

**How this could scale later.**
- Replace `BackgroundTasks` with a task queue (Celery/RQ + Redis) so jobs survive restarts and run on separate workers
- PostgreSQL instead of SQLite for concurrent writers
- Store PDFs in object storage (S3) and return signed URLs
- Authentication, per-user job ownership, rate limits, and an idempotency key against duplicate submissions

## Limitations (known and deliberate)

- **Latin characters only.** The built-in PDF fonts cannot print Devanagari, Chinese, etc.
  Such names fail *with a clear message* instead of printing garbage. Supporting them means
  registering a Unicode TTF font in `pdf_service.py`.
- **Jobs do not resume after a server restart** (limitation of in-process background tasks).
- No authentication; anyone who can reach the API can create jobs and download PDFs.
- Duplicate submissions create duplicate jobs.
- The ZIP is built in memory, fine for 1000 certificates, not for millions.
