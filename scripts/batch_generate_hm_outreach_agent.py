"""
Generate short hiring-manager outreach messages for archived jobs for a given day (default today).
Writes hm_outreach.txt in each job folder. Skips folders that already have hm_outreach.txt.

Alias: batchhm [YYYY-MM-DD]
"""
import os
import sys
from datetime import date
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


def iter_job_dirs_for_day(data_dir: Path, day: str):
    for company_dir in data_dir.iterdir():
        if not company_dir.is_dir():
            continue
        day_dir = company_dir / day
        if day_dir.is_dir():
            yield day_dir


def read_if_exists(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main():
    load_dotenv()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    day = date.today().isoformat()
    if len(sys.argv) == 2:
        day = sys.argv[1]

    data_dir = Path("data")
    resume_path = data_dir / "resume.txt"
    if not resume_path.exists():
        raise SystemExit("Missing data/resume.txt")

    resume_text = resume_path.read_text(encoding="utf-8")

    wrote = 0
    skipped = 0

    for job_dir in iter_job_dirs_for_day(data_dir, day):
        job_txt = job_dir / "job.txt"
        summary_md = job_dir / "company_summary.md"
        out_path = job_dir / "hm_outreach.txt"

        if not job_txt.exists() or out_path.exists():
            skipped += 1
            continue

        job_text = job_txt.read_text(encoding="utf-8")
        company_summary = read_if_exists(summary_md)

        prompt = f"""
            Draft a short hiring-manager outreach message.

            Constraints:
            - 3–5 sentences max
            - Professional, direct, human
            - No buzzwords
            - No overconfidence
            - No emojis
            - Assume cold outreach (LinkedIn or email)

            Goal:
            Express interest in the role, show light company understanding, and ask for a brief conversation.

            JOB DESCRIPTION:
            {job_text}

            COMPANY CONTEXT (if available):
            {company_summary}

            RESUME:
            {resume_text}

            Output plain text only.
            """.strip()

        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )

        text = msg.content[0].text.strip()
        if not text:
            continue

        out_path.write_text(text + "\n", encoding="utf-8")
        wrote += 1
        print(f"📧 Wrote {out_path}")

    print(f"\nDone. wrote={wrote} skipped={skipped}\n")


if __name__ == "__main__":
    main()