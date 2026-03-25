"""
Generate tailored resume bullets for a single job folder. Writes resume_bullets.json with placement
(section, role, replace/append) and bullets to add/remove. Single-job entry point; no args or date
delegates to batch script.

Invoked by: genbullets (batch). Single job: genbullets data/<company>/<date>
"""
import json
import os
import re
import sys
from datetime import datetime
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


def fix_literal_newlines_in_strings(json_str: str) -> str:
    """Replace unescaped newlines inside double-quoted string values with space (invalid in JSON)."""
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
    json_str = fix_literal_newlines_in_strings(json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from model (parse error: {e}). First 500 chars: {json_str[:500]!r}") from e


def _is_yyyy_mm_dd(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def resolve_job_dir(arg: str) -> Path:
    """
    Resolve input into a job folder containing job.txt.
    Supports:
      - direct job folder path (absolute/relative)
      - company slug (e.g., "costco") -> latest data/<company>/YYYY-MM-DD
    """
    candidate = Path(arg).resolve()
    if (candidate / "job.txt").exists():
        return candidate

    data_dir = (Path(__file__).resolve().parent.parent / "data").resolve()
    company_dir = (data_dir / arg).resolve()
    if company_dir.is_dir():
        dated_dirs = [
            p
            for p in company_dir.iterdir()
            if p.is_dir() and _is_yyyy_mm_dd(p.name) and (p / "job.txt").exists()
        ]
        if dated_dirs:
            return sorted(dated_dirs, key=lambda p: p.name)[-1]

    raise FileNotFoundError(
        f"Could not locate job folder for '{arg}'. "
        f"Expected either a direct path containing job.txt or data/<company>/YYYY-MM-DD/job.txt."
    )


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_bullets_agent.py <job_folder_path|company_slug>")
        raise SystemExit(1)

    load_dotenv()

    try:
        job_dir = resolve_job_dir(sys.argv[1])
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resume_loader import get_resume_text

    job_text = (job_dir / "job.txt").read_text(encoding="utf-8")
    resume_text = get_resume_text()

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
        You are tailoring resume bullets for a specific job. The candidate's base resume is TOO LONG (often by nearly half a page). Your output must help them both add/rewrite high-impact bullets AND cut enough content so the tailored resume fits.

        CRITICAL — Do NOT invent experience. Every tailored bullet MUST describe work that is explicitly or clearly implied on the resume. Do not add bullets about technologies, tools, or responsibilities the candidate has not used or done (e.g. do not add ASP.NET, C#, Windows Server, or similar if they do not appear on the resume). Never assume or invent that the candidate worked with the hiring company's products, internal teams, or JD-mentioned tools (e.g. "internal teams", "Claude Desktop", "Cowork", "Agent SDK") unless that experience is explicitly on the resume—do not infer collaboration or usage from the job description or company name. If the job description asks for something the resume does not support, do not invent a bullet for it; omit it or replace a less relevant bullet with one that reframes the candidate's actual experience. Each bullet must be grounded in specific resume content: same role/project, same or closely related technologies, same type of work.

        For each tailored bullet you must say WHERE on the resume it goes and whether to REPLACE an existing bullet or APPEND. You must also identify a THOROUGH list of existing resume bullets to REMOVE (least relevant to this job) so the resume can be shortened.

        Return ONLY valid JSON with this schema (no markdown, no code fences):
        {{
        "tailored_bullets": [
            {{
            "bullet": "<concise, impact-focused bullet>",
            "why_it_matches": "<one short sentence>",
            "placement": {{
              "section": "PROFESSIONAL EXPERIENCE" or "KEY PROJECTS",
              "role_or_project": "<exact role or project heading from the resume, e.g. Zulily, Full Stack Software Engineer (Vendor Team) or Underwater Acoustic Messaging Device>",
              "action": "replace" or "append",
              "replace_bullet_index": <if action is replace: the full text of the existing resume bullet to replace (copy exactly as it appears on the resume); if append: null>
            }}
            }}
        ],
        "bullets_to_remove": [
            {{
            "section": "PROFESSIONAL EXPERIENCE" or "KEY PROJECTS",
            "role_or_project": "<exact role or project heading from the resume>",
            "bullet_index": <full text of the existing resume bullet to remove (copy exactly as it appears on the resume)>,
            "reason": "<one short sentence: why this bullet is recommended for removal for this job, e.g. wrong focus, redundant, or not mentioned in JD>"
            }}
        ]
        }}

        Rules:
        - Escape double quotes inside strings with backslash. No newlines inside JSON string values.
        - tailored_bullets: 6–10 bullets. Map each to a real section/role or project from the resume; do not invent sections. Use strong action verbs and quantified impact. Align tightly to the job description. Every bullet must reframe or reword ONLY experience that appears on the resume—no made-up technologies, roles, or accomplishments.
        - Do NOT suggest appending a bullet that already exists on the resume (verbatim or near-duplicate). Check the RESUME section: if a bullet with the same or nearly the same content is already there, do not include it as a tailored bullet. Only suggest bullets that are meaningfully reworded/reframed for this JD or that combine/synthesize existing points; never duplicate an existing bullet.
        - placement.role_or_project must match the resume exactly (e.g. "Zulily, Full Stack Software Engineer (Vendor Team) – Seattle, WA | Mar 2022 – Dec 2023" or the project name under KEY PROJECTS).
        - Use "replace" when a tailored bullet is a better fit than an existing bullet; use "append" when adding to a role/project that has few bullets. You must include at least 2–4 "replace" actions (not only append): identify existing bullets that are weak for this JD and replace them with tailored ones. replace_bullet_index: when action is "replace", use the full bullet text exactly as it appears on the resume (copy the whole line).
        - bullets_to_remove: List only 3–6 existing resume bullets that are clearly redundant or off-focus. Do not remove more than you replace. bullet_index: use the full bullet text exactly as it appears on the resume (copy the whole line). Reference each by section, role_or_project (exact match), bullet_index (full bullet text), and reason.

        JOB DESCRIPTION:
        {job_text}

        RESUME:
        {resume_text}
        """.strip()

    for attempt in range(2):
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (msg.content[0].text or "").strip()
        try:
            data = parse_bullets_json(raw)
            break
        except ValueError as e:
            if attempt == 0:
                print("  Parse failed, retrying once…", file=sys.stderr)
                prompt = prompt + "\n\nImportant: Return only valid JSON. Inside every string value, escape double quotes with \\ and do not include literal newlines; use \\n for line breaks if needed."
            else:
                print(f"Parse error: {e}", file=sys.stderr)
                raise SystemExit(1)

    if "tailored_bullets" not in data or not isinstance(data["tailored_bullets"], list):
        print("Model did not return tailored_bullets array.", file=sys.stderr)
        raise SystemExit(1)

    # Ensure bullets_to_remove exists (default to empty array if missing)
    if "bullets_to_remove" not in data:
        data["bullets_to_remove"] = []
    elif not isinstance(data["bullets_to_remove"], list):
        print("Warning: bullets_to_remove should be an array, defaulting to empty.", file=sys.stderr)
        data["bullets_to_remove"] = []

    out_path = job_dir / "resume_bullets.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📝 Wrote {out_path}\n")


if __name__ == "__main__":
    main()