"""
Check if a job posting (job_dir/job.txt) requires or prefers security clearance by phrase matching.
Exit 0 = no clearance required, 1 = clearance required. Used by popjobs and initial_fit_score_agent.

Invoked by: popjobs, initial_fit_score_agent (no direct alias).
"""
import sys
from pathlib import Path

# Phrases that indicate the job requires or prefers security clearance (case-insensitive).
SECURITY_CLEARANCE_PHRASES = [
    "security clearance",
    "secret clearance",
    "top secret",
    "ts/sci",
    "ts-sci",
    "clearance required",
    "must have clearance",
    "must possess clearance",
    "active clearance",
    "active secret",
    "active top secret",
    "eligible for clearance",
    "clearance eligibility",
    "dod clearance",
    "dod secret",
    "government clearance",
    "federal clearance",
    "polygraph",
    "security clearance required",
]


def requires_security_clearance(job_dir: Path) -> bool:
    """Return True if job.txt in job_dir indicates a security clearance requirement."""
    job_txt = job_dir / "job.txt"
    if not job_txt.exists():
        return False
    text = job_txt.read_text(encoding="utf-8").lower()
    return any(phrase.lower() in text for phrase in SECURITY_CLEARANCE_PHRASES)


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/check_security_clearance.py <job_folder_path>", file=sys.stderr)
        raise SystemExit(2)
    job_dir = Path(sys.argv[1])
    raise SystemExit(1 if requires_security_clearance(job_dir) else 0)


if __name__ == "__main__":
    main()
