# Interview Guide - Bulk Certificate Generator

## A. "Tell me about your project" (about 2 minutes)

> "I built a backend API that generates certificates in bulk. An organization can send one
> request with, say, 500 participants plus the event name and date, and the system creates a
> PDF certificate for each person from a predefined template.
>
> I used **FastAPI** with **SQLAlchemy and SQLite**. When a request arrives, Pydantic
> validates the structure, then I save a **job** row and one **certificate** row per recipient
> and immediately return a job ID with status `queued`. The actual PDF generation runs in a
> **background task**, so the client never waits on a long request.
>
> The background task goes through the recipients one by one. Each one is validated and
> rendered inside its own try/except and its own database transaction. If one fails, say it
> has an invalid email or a name the font can't print, I record the reason on that
> certificate and **keep going**. So the job ends as `completed`, `completed_with_errors`, or
> `failed`, and the client can poll a status endpoint to see progress percentage, how many
> succeeded and failed, and exactly why each failure happened.
>
> To make the PDFs I use a template PDF and overlay the recipient's name, event, date and a
> unique certificate ID with ReportLab, then merge them with pypdf. Clients can download one
> PDF or a ZIP of all successful ones.
>
> I wrote pytest tests for every area the assignment listed, including one that proves
> recipient A succeeds, B fails, C still succeeds. I deliberately kept it simple: no Celery or
> Redis. In the README I explain why, and how I would add them for production."

## B. Request flow

```
Client
  -> POST /api/v1/certificates/jobs
  -> FastAPI + Pydantic validate the body (bad structure => 422, stop)
  -> certificate_service.create_job: save 1 job + N certificates (status pending)
  -> respond 202 {job_id, status: queued, total}          <- the client is free now
  -> BackgroundTasks runs GenerationService.process_job
        job.status = processing
        for each certificate:
            validate recipient -> render PDF -> save file
            success => status=success, file_path saved
            failure => status=failed, error_message saved   (loop continues)
            commit (progress is now visible)
        recount results, job.status = completed / completed_with_errors / failed
Client
  -> GET /jobs/{id}                  progress, counters, failures
  -> GET /jobs/{id}/certificates     per-recipient list
  -> GET /certificates/{id}          the PDF  (or /jobs/{id}/download for a ZIP)
```

## C. Likely questions and simple answers

**1. Why FastAPI?**
It validates input automatically with Pydantic, generates Swagger docs for free, and is
fast to write and test. The assignment allowed FastAPI, Django or Flask; FastAPI needs the
least boilerplate for a pure API.

**2. Why background processing?**
A request can contain hundreds of recipients. Doing all the work before replying could take
long enough that the client times out. So I save the job, reply instantly with a job ID, and
generate in the background. The client checks progress separately.

**3. Why a relational database?**
The data is related: one job has many certificates. I need counters, filtering ("all failed
in job 7") and consistent updates in transactions. A relational database does all of this
naturally.

**4. Why SQLite?**
It needs no installation, which makes the project easy for a reviewer to run. Because I use
SQLAlchemy, moving to PostgreSQL is mostly changing `DATABASE_URL`.

**5. How does bulk processing work?**
One POST holds a list of recipients. They become rows in the database, and one background
task loops through them sequentially, generating one PDF per recipient.

**6. How is progress calculated?**
`progress = completed * 100 // total`, where `completed` = successful + failed. I commit
after every certificate, so a status request during the run shows live progress.

**7. What happens if one certificate fails?**
That certificate gets `status=failed` and an `error_message`, the job's failed counter goes
up, and processing continues with the next recipient. At the end the job becomes
`completed_with_errors`.

**8. How do you prevent one failure from stopping the job?**
Three layers: (a) each recipient is processed inside its own try/except; (b) each one has its
own database session and commit; (c) the loop itself also wraps the call in a try/except in
case saving the result fails. And `process_job` never raises to the framework.

**9. How is validation done?**
Two levels. Pydantic validates the request structure (non-empty recipients, event name, date
format, max 1000 recipients) and returns 422 on failure. Then each recipient is validated by
a stricter Pydantic model (name not blank, email format). A bad recipient doesn't reject the
request; it becomes a failed certificate with a clear reason.

**10. Why not reject the whole request when one recipient is invalid?**
The assignment says one bad recipient shouldn't block the valid ones. Rejecting everything
would force the client to fix and resend 500 records because of one typo. Recording the
failure also means nobody silently disappears. (If the interviewer wants strict behavior,
it's a small change; see question 22.)

**11. How are generated files stored?**
On disk in `generated/job_<id>/<certificate_code>.pdf`; the path is saved in the certificate
row. File names use the random code, not the recipient name, so user input can't affect where
a file is written.

**12. How exactly is text placed on the certificate?**
The template PDF has the fixed design. For each recipient ReportLab draws the name, event,
date and ID at fixed coordinates on a blank page of the same size, and pypdf merges that onto
the template. If a name is too long, the font size shrinks until it fits.

**13. How would you scale this?**
Move generation to a task queue with several workers, use PostgreSQL, store PDFs in object
storage like S3, and add pagination everywhere. The architecture already separates routes,
services, and PDF code, so each piece can be swapped independently.

**14. How would you use PostgreSQL?**
Set `DATABASE_URL=postgresql+psycopg2://user:pass@host/db` and install `psycopg2-binary`. The
models are standard SQLAlchemy. I'd add Alembic migrations instead of `create_all`.

**15. How would you use Celery and Redis in production?**
The route would call `process_job.delay(job.id)` instead of `BackgroundTasks.add_task`. Redis
holds the queue, and separate worker processes consume it. Jobs would then survive web-server
restarts, could be retried, and could run in parallel. I didn't add it here because it adds
infrastructure the assignment doesn't need.

**16. How would you handle 10,000 recipients?**
Use a queue with workers, split the job into chunks (e.g. 100 per task) processed in parallel,
write the ZIP to disk or object storage instead of memory, and paginate the listing (already
supported with `limit`/`offset`). I'd also raise or remove the 1000-recipient limit
deliberately, not accidentally.

**17. How would you prevent duplicate jobs?**
Accept an `Idempotency-Key` header, store it on the job with a unique constraint, and return
the existing job if the same key arrives again. Alternatively hash the payload and compare
against recent jobs.

**18. How would you secure certificate downloads?**
Add authentication (e.g. JWT), tie each job to its owner, and check ownership on every
endpoint. For public sharing, issue short-lived signed URLs. Certificate codes are random, but
sequential integer IDs in URLs are guessable, so ownership checks matter.

**19. How would you handle concurrent requests?**
Each request has its own DB session, and each job uses its own sessions in the background, so
jobs don't share state. SQLite allows one writer at a time (I set a 30 s busy timeout and WAL
mode), which is fine here. PostgreSQL handles concurrent writers properly.

**20. What would you improve for production?**
Authentication, a real task queue, Alembic migrations, PDF storage in S3, Unicode font
support, retry for failed certificates, email delivery of certificates, rate limiting,
structured logging and metrics.

**21. What happens if the server restarts during a job?**
With in-process background tasks, the job stops, and its status stays `processing` with some
certificates `pending`. A queue like Celery fixes this. A cheap fix: at startup, find jobs
stuck in `processing` and re-queue their pending certificates. That is a known limitation
documented in the README.

**22. The interviewer says: "Make invalid recipients reject the whole request." What do you change?**
Move the checks from `recipient_validation.py` into the `RecipientIn` Pydantic model as
`field_validator`s (blank name, email format). Then FastAPI automatically returns 422 before
anything is saved. I'd update the tests in `test_validation.py` that currently expect a 202
with failed certificates.

**23. How do you make sure the failure test is meaningful?**
I use a `FailingRenderer` that subclasses the real renderer and raises only for one name,
so every other recipient goes through real PDF generation. Then I assert both statuses, the
counters, the stored error message, and that the files for the recipients after the failure
exist. A second test moves the failure to every position in a list of seven.

**24. Why does `GenerationService` open its own database sessions?**
It runs after the HTTP response is sent, when the request's session is already closed.
Sharing a request-scoped session across threads is also unsafe.

**25. Why 202 instead of 201 for creating a job?**
201 means "created and finished". 202 means "accepted, processing continues later", which
is exactly what happens.

**26. How do you hide internal errors?**
Known errors map to specific status codes with clean messages. Unknown exceptions are logged
with the full stack trace on the server, while the client sees "Internal server error" (or a
generic per-certificate message). A test checks that a secret in an exception message never
reaches the client.

**27. Why do job counters exist when you could count certificate rows?**
Reading three integers is faster than counting thousands of rows on every poll. At the end of
the job I recount from the rows anyway, so the counters can't drift.

**28. How do you change the template?**
Edit and rerun `scripts/create_template.py`, or replace the PDF. If text positions change,
update the coordinate constants at the top of `pdf_service.py`.

## D. Where to look if asked to modify something

| Change request | File |
|---|---|
| Different validation rule | `app/schemas/certificate.py`, `recipient_validation.py` |
| New field on certificate (e.g. course hours) | `schemas`, `models.py`, `pdf_service.py` (+ template) |
| Different text position/font | top of `pdf_service.py` |
| New status | `db/models.py`, `generation_service.decide_final_status` |
| Retry failed certificates | new method in `generation_service.py` + one route |
| Use PostgreSQL | `DATABASE_URL` in `.env` |
