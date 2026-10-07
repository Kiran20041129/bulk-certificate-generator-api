"""Demo: submit sample_data/demo_request.json to a RUNNING server and show the result.

1. In one terminal:  uvicorn app.main:app --reload
2. In another:       python scripts/demo.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/certificates"
SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "demo_request.json"


def main() -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with httpx.Client(timeout=30) as client:
        try:
            created = client.post(f"{BASE_URL}/jobs", json=payload)
        except httpx.ConnectError:
            sys.exit("Server not running. Start it with: uvicorn app.main:app --reload")
        created.raise_for_status()
        job_id = created.json()["job_id"]
        print(f"Created job {job_id}: {created.json()}")

        while True:  # poll until the background job finishes
            status = client.get(f"{BASE_URL}/jobs/{job_id}").json()
            print(f"  status={status['status']:<22} progress={status['progress']}%")
            if status["status"] not in ("queued", "processing"):
                break
            time.sleep(0.5)

        print(f"\nSuccessful: {status['successful']}  Failed: {status['failed']}")
        for failure in status["failures"]:
            print(f"  FAILED  {failure['recipient_name']!r}: {failure['error']}")

        out_dir = Path("demo_output")
        out_dir.mkdir(exist_ok=True)
        listing = client.get(f"{BASE_URL}/jobs/{job_id}/certificates").json()
        for cert in listing["certificates"]:
            if cert["file_available"]:
                pdf = client.get(f"http://127.0.0.1:8000{cert['download_url']}")
                target = out_dir / f"{cert['certificate_code']}.pdf"
                target.write_bytes(pdf.content)
                print(f"  saved   {cert['recipient_name']} -> {target}")


if __name__ == "__main__":
    main()
