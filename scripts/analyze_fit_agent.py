import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/analyze_fit_agent.py <job_folder_path>")
        raise SystemExit(1)

    load_dotenv()

    job_dir = Path(sys.argv[1])
    job_txt = job_dir / "job.txt"
    resume_txt = Path("data") / "resume.txt"

    job_text = job_txt.read_text(encoding="utf-8")
    resume_text = resume_txt.read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
        Return ONLY valid JSON with this exact schema:
        {{
        "fit_score_0_to_100": <number>,
        "must_have_keywords": [<string>],
        "nice_to_have_keywords": [<string>],
        "missing_keywords_from_resume": [<string>],
        "top_resume_points_to_emphasize": [<string>]
        }}

        JOB DESCRIPTION:
        {job_text}

        RESUME:
        {resume_text}
        """.strip()

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()

    # Debug: show what Claude actually returned (first 400 chars)
    if not raw:
        raise RuntimeError("Claude returned empty output.")
    print("\n--- Claude raw output (first 400 chars) ---")
    print(raw[:400])
    print("--- end ---\n")

    # Try strict JSON first, then fallback to extracting JSON from a larger blob
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])

    out_path = job_dir / "fit.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n ✅ Wrote {out_path}\n")


if __name__ == "__main__":
    main()