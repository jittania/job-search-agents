"""
Extract job metadata for sheet columns: role title, company type, company size bucket, role focus, role level.
Company type is classified by rubric (search + job posting; employee count alone must not determine it).
Company size bucket is derived from employee count when stated, else from LLM. Outputs JSON only (no sheet write).

Invoked by: popjobs, batchmetadata.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Extraction logic lives in batch_extract_metadata; this script is the single-job entry point.
from batch_extract_metadata import extract_metadata_for_job_dir


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/extract_job_metadata_agent.py <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()
    job_dir = Path(sys.argv[1])
    job_txt = job_dir / "job.txt"
    if not job_txt.exists():
        print(f"No job.txt at {job_dir}", file=sys.stderr)
        raise SystemExit(2)

    data, _ = extract_metadata_for_job_dir(job_dir)
    print(json.dumps(data))


if __name__ == "__main__":
    main()
