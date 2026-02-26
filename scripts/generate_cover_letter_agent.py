"""
Generate a cover letter for a single job folder. Writes cover_letter.md (and optionally uploads .docx).
Single-job entry point. Use --overwrite to replace existing cover_letter.md.

Invoked by: gencl (batch). Single job: gencl data/<company>/<date>
"""
import os
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


def main():
    args = [a for a in sys.argv[1:] if a != "--overwrite"]
    overwrite = "--overwrite" in sys.argv[1:]
    if len(args) != 1:
        print("Usage: python scripts/generate_cover_letter_agent.py <job_folder> [--overwrite]")
        raise SystemExit(1)

    job_dir = Path(args[0])
    if not job_dir.exists():
        raise SystemExit(f"Folder not found: {job_dir}")

    job_txt = job_dir / "job.txt"
    url_txt = job_dir / "url.txt"
    out_path = job_dir / "cover_letter.md"

    if out_path.exists() and not overwrite:
        raise SystemExit(f"cover_letter.md already exists in {job_dir}")

    if not job_txt.exists():
        raise SystemExit("Missing job.txt")

    resume_path = Path("data/resume.txt")
    if not resume_path.exists():
        raise SystemExit("Missing data/resume.txt")

    load_dotenv()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    job_text = job_txt.read_text(encoding="utf-8")
    resume_text = resume_path.read_text(encoding="utf-8")
    url = url_txt.read_text(encoding="utf-8").strip() if url_txt.exists() else ""

    prompt = f"""
        Write a concise, confident cover letter tailored to this job.

        Constraints:
        - 220–320 words
        - 3 short paragraphs max
        - No buzzword soup
        - No claims you can't support from the resume
        - Reference the company/role naturally (if the JD provides it)
        - End with a simple call to action
        - Output plain text ONLY

        JOB POSTING URL (if available):
        {url}

        JOB DESCRIPTION:
        {job_text}

        RESUME:
        {resume_text}
        """.strip()

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )

    letter = msg.content[0].text.strip()
    if not letter:
        raise SystemExit("Model returned empty output")

    out_path.write_text(letter + "\n", encoding="utf-8")
    print(f"\n✍️ Wrote {out_path}\n")


if __name__ == "__main__":
    main()