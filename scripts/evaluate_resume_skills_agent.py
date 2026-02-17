"""
Evaluate the TECHNICAL SKILLS section of the resume for a specific job. Recommendations are
tailored to this job description: what to omit (low relevance for this role) and what to add
(JD-relevant skills the candidate has but didn't list, or that strengthen the match).

Writes <job_folder>/skills_recommendations.json.
- No args or "today" or YYYY-MM-DD → batch for that day (delegates to batch script).
- One arg that is a job folder path → single job.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

RESUME_PATH = Path("data/resume.txt")
OUTPUT_FILE = "skills_recommendations.json"


def strip_markdown_code_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def fix_trailing_commas(json_str: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", json_str)


def parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Model returned empty output")
    raw = strip_markdown_code_fences(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found (first 200 chars: {raw[:200]!r})")
    json_str = raw[start : end + 1]
    json_str = fix_trailing_commas(json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}. First 500 chars: {json_str[:500]!r}") from e


def main():
    script_dir = Path(__file__).resolve().parent
    batch_script = script_dir / "batch_evaluate_resume_skills_agent.py"

    # No args → batch for today (so "evalskills" works whether alias points here or at batch script)
    if len(sys.argv) == 1:
        subprocess.run([sys.executable, str(batch_script)], check=True)
        return
    # One arg that looks like "today" or YYYY-MM-DD → batch for that day
    if len(sys.argv) == 2:
        arg = sys.argv[1].strip().lower()
        if arg == "today" or (len(arg) == 10 and arg[4] == "-" and arg[7] == "-"):
            subprocess.run([sys.executable, str(batch_script), sys.argv[1]], check=True)
            return
    # One arg that is a job folder path → single job; else usage
    if len(sys.argv) != 2:
        print("Usage: python scripts/evaluate_resume_skills_agent.py [today|YYYY-MM-DD]  OR  <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)
    job_dir = Path(sys.argv[1]).resolve()
    if not (job_dir / "job.txt").exists():
        print("Usage: python scripts/evaluate_resume_skills_agent.py [today|YYYY-MM-DD]  OR  <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()
    job_txt = job_dir / "job.txt"
    if not RESUME_PATH.exists():
        print(f"Resume not found at {RESUME_PATH}. Run from project root.", file=sys.stderr)
        raise SystemExit(1)

    job_text = job_txt.read_text(encoding="utf-8")
    resume_text = RESUME_PATH.read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
You are evaluating the candidate's TECHNICAL SKILLS section for a specific job. Recommend changes so the skills list is better tailored to THIS role.

Your task:
1. **Skills to consider omitting** — From the current TECHNICAL SKILLS section, list any that are low relevance for THIS job, redundant, or that dilute focus for this role. For each, give a short reason tied to the job description.
2. **Skills to consider adding** — Skills mentioned in the job description or strongly implied by it that the candidate clearly has (from experience/projects on the resume) but did NOT list in TECHNICAL SKILLS. Also suggest common pairings for this role they could add if they have them. For each, give a short reason (e.g. "JD asks for X" or "Used in Project Y; relevant to this role"). Only suggest skills they can honestly claim from the resume.

Return ONLY valid JSON with this schema (no markdown, no code fences). Escape double quotes in strings. No newlines inside string values.

{{
  "skills_to_consider_omitting": [
    {{ "skill": "<exact phrase from resume>", "reason": "<why for this job>" }}
  ],
  "skills_to_consider_adding": [
    {{ "skill": "<skill name>", "reason": "<why for this job / where on resume>" }}
  ]
}}

If there are no suggestions for one category, use an empty array. Be concise; 3–6 items per category is enough.

JOB DESCRIPTION:
{job_text[:30000]}

RESUME:
{resume_text[:20000]}
""".strip()

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (msg.content[0].text or "").strip()
    try:
        data = parse_json(raw)
    except ValueError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        raise SystemExit(1)

    for key in ("skills_to_consider_omitting", "skills_to_consider_adding"):
        if key not in data or not isinstance(data[key], list):
            data[key] = []

    out_path = job_dir / OUTPUT_FILE
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📋 Wrote {out_path}\n")


if __name__ == "__main__":
    main()
