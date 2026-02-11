import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


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

        Return ONLY valid JSON with this schema:
        {{
        "tailored_bullets": [
            {{
            "bullet": "<concise, impact-focused bullet>",
            "why_it_matches": "<one short sentence>"
            }}
        ]
        }}

        Rules:
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

    raw = msg.content[0].text.strip()

    # Robust JSON parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        data = json.loads(raw[start : end + 1])

    out_path = job_dir / "resume_bullets.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📝 Wrote {out_path}\n")


if __name__ == "__main__":
    main()