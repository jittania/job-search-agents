"""Extract job metadata for sheet columns: role title, company type, size bucket, role focus, role level."""
import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# Allowed values matching your sheet dropdowns (used in prompt)
COMPANY_TYPES = ["STARTUP", "BIG TECH", "GOV", "SCALE-UP"]
COMPANY_SIZE_BUCKETS = ["<50", "50-200", "200-1000", "1000+"]
ROLE_FOCUS_OPTIONS = ["FRONTEND", "BACKEND", "FULL-STACK", "EMBEDDED", "ML"]
ROLE_LEVEL_OPTIONS = ["JUNIOR", "MID", "SENIOR", "STAFF", "PRINCIPAL"]


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/extract_job_metadata.py <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()
    job_dir = Path(sys.argv[1])
    job_txt = job_dir / "job.txt"
    if not job_txt.exists():
        print(f"No job.txt at {job_dir}", file=sys.stderr)
        raise SystemExit(2)

    job_text = job_txt.read_text(encoding="utf-8")[:30000]

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""From the job posting below, extract metadata. Return ONLY valid JSON with exactly these keys (use only the allowed values where listed):

- "role_title": string, the exact job title from the posting (e.g. "Senior Software Engineer").
- "company_type": exactly one of {json.dumps(COMPANY_TYPES)} (STARTUP, BIG TECH, GOV, SCALE-UP). Pick the best match.
- "company_size_bucket": exactly one of {json.dumps(COMPANY_SIZE_BUCKETS)}. Infer from job or company context if not stated.
- "role_focus": exactly one of {json.dumps(ROLE_FOCUS_OPTIONS)} (FRONTEND, BACKEND, FULL-STACK, EMBEDDED, ML). Pick the best match.
- "role_level": exactly one of {json.dumps(ROLE_LEVEL_OPTIONS)} (JUNIOR, MID, SENIOR, STAFF, PRINCIPAL). Infer from title/requirements.

No other keys. No explanation.

JOB POSTING:
{job_text}
"""

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (msg.content[0].text or "").strip()
    if not raw:
        raise RuntimeError("Claude returned empty output.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])

    # Normalize to allowed values (exact match or contains)
    def pick(allowed: list[str], key: str, default: str) -> str:
        val = (data.get(key) or "").strip()
        if not val:
            return default
        val_upper = val.upper().replace(" ", "")
        for a in allowed:
            if a.upper() == val.upper() or a.upper().replace(" ", "") in val_upper or val_upper in a.upper().replace(" ", ""):
                return a
        return default

    out = {
        "role_title": (data.get("role_title") or "").strip() or "Unknown",
        "company_type": pick(COMPANY_TYPES, "company_type", "STARTUP"),
        "company_size_bucket": pick(COMPANY_SIZE_BUCKETS, "company_size_bucket", "1000+"),
        "role_focus": pick(ROLE_FOCUS_OPTIONS, "role_focus", "FULL-STACK"),
        "role_level": pick(ROLE_LEVEL_OPTIONS, "role_level", "SENIOR"),
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
