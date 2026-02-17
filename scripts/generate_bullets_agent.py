import json
import os
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


def strip_markdown_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers."""
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
    """Remove trailing commas before ] or } so strict JSON parsers accept it."""
    return re.sub(r",(\s*[}\]])", r"\1", json_str)


def parse_bullets_json(raw: str) -> dict:
    """Parse LLM output into a dict; strip markdown and fix common JSON issues."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Model returned empty output")
    raw = strip_markdown_code_fences(raw)
    # Extract the outermost {...}
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in output (first 200 chars: {raw[:200]!r})")
    json_str = raw[start : end + 1]
    json_str = fix_trailing_commas(json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from model (parse error: {e}). First 500 chars: {json_str[:500]!r}") from e


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_bullets_agent.py <job_folder_path>")
        raise SystemExit(1)

    load_dotenv()

    job_dir = Path(sys.argv[1])
    job_text = (job_dir / "job.txt").read_text(encoding="utf-8")
    resume_text = Path("data/resume.txt").read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
        You are tailoring resume bullets for a specific job.

        Return ONLY valid JSON with this schema (no markdown, no code fences):
        {{
        "tailored_bullets": [
            {{
            "bullet": "<concise, impact-focused bullet>",
            "why_it_matches": "<one short sentence>"
            }}
        ]
        }}

        Rules:
        - Escape double quotes inside strings with backslash. No newlines inside JSON string values.
        - 6–8 bullets max
        - Use strong action verbs
        - Prefer quantified impact when possible
        - Align bullets tightly to the job description
        - Do NOT invent experience

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

    raw = (msg.content[0].text or "").strip()
    try:
        data = parse_bullets_json(raw)
    except ValueError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if "tailored_bullets" not in data or not isinstance(data["tailored_bullets"], list):
        print("Model did not return tailored_bullets array.", file=sys.stderr)
        raise SystemExit(1)

    out_path = job_dir / "resume_bullets.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📝 Wrote {out_path}\n")


if __name__ == "__main__":
    main()