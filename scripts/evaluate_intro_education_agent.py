"""
Evaluate the resume INTRO (summary paragraph) and EDUCATION section for relevancy to a specific job.
Writes <job_folder>/intro_education_recommendations.json. No args or today/YYYY-MM-DD delegates to batch.

Alias: evalintroedu [today|YYYY-MM-DD] or evalintroedu data/<company>/<date>
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

OUTPUT_FILE = "intro_education_recommendations.json"


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


def fix_literal_newlines_in_strings(json_str: str) -> str:
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(json_str):
        c = json_str[i]
        if escape_next:
            result.append(c)
            escape_next = False
        elif c == "\\" and in_string:
            result.append(c)
            escape_next = True
        elif c == '"' and not escape_next:
            in_string = not in_string
            result.append(c)
        elif c == "\n" and in_string:
            result.append(" ")
        else:
            result.append(c)
        i += 1
    return "".join(result)


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
    json_str = fix_literal_newlines_in_strings(json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}. First 500 chars: {json_str[:500]!r}") from e


def main():
    script_dir = Path(__file__).resolve().parent
    batch_script = script_dir / "batch_evaluate_intro_education_agent.py"

    if len(sys.argv) == 1:
        subprocess.run([sys.executable, str(batch_script)], check=True)
        return
    if len(sys.argv) == 2:
        arg = sys.argv[1].strip().lower()
        if arg == "today" or (len(arg) == 10 and arg[4] == "-" and arg[7] == "-"):
            subprocess.run([sys.executable, str(batch_script), sys.argv[1]], check=True)
            return
    if len(sys.argv) != 2:
        print("Usage: python scripts/evaluate_intro_education_agent.py [today|YYYY-MM-DD]  OR  <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)
    job_dir = Path(sys.argv[1]).resolve()
    if not (job_dir / "job.txt").exists():
        print("Usage: python scripts/evaluate_intro_education_agent.py [today|YYYY-MM-DD]  OR  <job_folder_path>", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()
    sys.path.insert(0, str(script_dir))
    from resume_loader import get_resume_text
    try:
        resume_text = get_resume_text()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    job_text = (job_dir / "job.txt").read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
You are evaluating the candidate's resume INTRO (the summary/headline paragraph under their name) and EDUCATION section for relevancy to a specific job. Recommend what to emphasize, trim, or adjust so these sections align better with THIS job description.

Your task:
1. **Intro** — Assess how well the current summary paragraph matches the role (keywords, focus, level). Suggest specific changes: phrases to emphasize or add (JD-aligned), phrases to trim or soften if they dilute focus for this role, and optionally a one-line suggested rewrite or key phrase to include.
2. **Education** — For each education entry, note relevance to this job (high/medium/low) and a short suggestion (e.g. "lead with this" or "optional to shorten" or "irrelevant for this role; keep for completeness"). Do not invent or remove real entries; only recommend emphasis or brevity.

Return ONLY valid JSON with this schema (no markdown, no code fences). Escape double quotes in strings with backslash. Do not include literal newlines inside any string value.

{{
  "intro": {{
    "relevancy_notes": "<2-4 sentences: how well the intro aligns with this JD>",
    "suggestions": [
      {{ "type": "emphasize" or "trim" or "add", "text": "<phrase or idea>", "reason": "<why for this job>" }}
    ],
    "optional_rewrite_phrase": "<one optional sentence or phrase the candidate could use in the intro, or null>"
  }},
  "education": {{
    "relevancy_notes": "<1-3 sentences: how relevant the education block is for this role>",
    "entries": [
      {{ "entry": "<exact education line from resume>", "relevance": "high" or "medium" or "low", "suggestion": "<short recommendation>" }}
    ]
  }}
}}

Be concise. 2-5 intro suggestions is enough. One suggestion per education entry. If optional_rewrite_phrase is not needed, use null.

JOB DESCRIPTION:
{job_text[:30000]}

RESUME:
{resume_text[:20000]}
""".strip()

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = (msg.content[0].text or "").strip()
    try:
        data = parse_json(raw)
    except ValueError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if "intro" not in data or not isinstance(data["intro"], dict):
        data["intro"] = {}
    data["intro"].setdefault("relevancy_notes", "")
    data["intro"].setdefault("suggestions", [])
    data["intro"].setdefault("optional_rewrite_phrase", None)
    if "education" not in data or not isinstance(data["education"], dict):
        data["education"] = {}
    data["education"].setdefault("relevancy_notes", "")
    data["education"].setdefault("entries", [])

    out_path = job_dir / OUTPUT_FILE
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📋 Wrote {out_path}\n")


if __name__ == "__main__":
    main()
