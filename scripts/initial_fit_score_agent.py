"""Score a single job 0-100 (initial fit score only). Used by batch_initial_fit_score."""
import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/initial_fit_score_agent.py <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()

    job_dir = Path(sys.argv[1])
    job_txt = job_dir / "job.txt"
    resume_txt = Path("data") / "resume.txt"

    if not job_txt.exists():
        print(f"No job.txt at {job_dir}", file=sys.stderr)
        raise SystemExit(2)

    job_text = job_txt.read_text(encoding="utf-8")
    resume_text = resume_txt.read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = """
Return ONLY valid JSON with this exact schema:
{"fit_score_0_to_100": <number>}

Score from 0 to 100 how well the candidate's resume fits this job. Be CONSERVATIVE: use the full range and prefer the lower end of a band when uncertain. Most jobs should fall between 25 and 65; reserve high scores for clear, strong matches only.

Rubric:
- 90-100: Rare. Nearly perfect fit — all must-have requirements clearly met and exceeded; level, focus, and domain align very well; no material gaps.
- 75-89: Strong fit — all key requirements met; at most minor gaps. Only use when the match is clearly strong.
- 55-74: Moderate fit — some requirements met but notable gaps in skills, level, or focus. Default here when fit is decent but not clearly strong.
- 35-54: Weak fit — significant gaps; important requirements missing or mismatched.
- 0-34: Poor fit — major mismatches in level, skills, or focus; not a realistic match.

Consider: required skills vs resume, experience level (e.g. senior vs mid), role focus (e.g. backend vs fullstack), and industry/domain relevance. When in doubt, score lower. No other fields.

JOB DESCRIPTION:
""" + job_text[:50000] + """

RESUME:
""" + resume_text[:20000]

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt.strip()}],
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

    score = data.get("fit_score_0_to_100")
    if score is None:
        raise RuntimeError(f"Claude did not return fit_score_0_to_100: {data}")

    # Clamp to 0-100 and print only the number (for batch script to capture)
    score = max(0, min(100, int(round(score))))
    print(score)


if __name__ == "__main__":
    main()
