"""
Evaluate the TECHNICAL SKILLS section of the resume for a specific job. Writes
<job_folder>/skills_recommendations.json (omit/add recommendations tailored to the JD).
No args or today/YYYY-MM-DD delegates to batch script.

Alias: evalskills [today|YYYY-MM-DD] or evalskills data/<company>/<date>
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

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


def fix_escaped_apostrophes(json_str: str) -> str:
    """Replace \\' with ' (invalid in JSON; apostrophes need no escape inside double-quoted strings)."""
    return json_str.replace("\\'", "'")


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
    json_str = fix_escaped_apostrophes(json_str)
    json_str = fix_literal_newlines_in_strings(json_str)
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
    sys.path.insert(0, str(script_dir))
    from resume_loader import get_resume_text
    try:
        resume_text = get_resume_text()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    job_text = job_txt.read_text(encoding="utf-8")

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""
You are evaluating the candidate's TECHNICAL SKILLS section for a specific job. The candidate's base resume is TOO LONG (often by nearly half a page). Your main job is to recommend what to CUT so the skills section is shorter and tightly aligned to THIS role.

**Scope of TECHNICAL SKILLS:** The TECHNICAL SKILLS section is the block that starts with the line "TECHNICAL SKILLS" and ends right before the line "PROFESSIONAL EXPERIENCE". It includes every subsection and line in between: AI-Augmented Development, Programming Languages, Frameworks & Libraries, Databases (if present), Tools & Cloud Services, Development Practices, and any other lines. You MUST review every one of these lines—do not skip Development Practices or any subsection.

Your tasks:
1. **Skills to consider omitting** — Consider ONLY the TECHNICAL SKILLS block (as defined above). List every skill or phrase from that block that is low relevance for THIS job, redundant, or dilutes focus. CRITICAL: Only list items that actually appear in the TECHNICAL SKILLS block. Use the exact phrase as it appears there (e.g. "PHP", "Kibana", "REST APIs"). Do NOT recommend omitting anything that appears only in the rest of the resume (e.g. in experience bullets)—if a tech appears in bullets but not in TECHNICAL SKILLS, do not list it under omit. Aim for 8–18 items. For each item include:
   - "skill": exact phrase as it appears in the TECHNICAL SKILLS block.
   - "reason": one sentence tied to the job description (why it's safe to cut for this role).
   - "priority": one of "cut_first", "recommended", or "optional".
2. **Skills to consider adding** — Skills the JD explicitly or strongly implies that the candidate clearly has (from experience/projects on the resume) but did NOT list in the TECHNICAL SKILLS block. CRITICAL: Before suggesting any add, verify that the skill does NOT already appear anywhere in the TECHNICAL SKILLS block—check every line including Programming Languages, Tools & Cloud Services, Development Practices, etc. (e.g. if SQL or AWS already appear there, do not suggest adding them). Only suggest skills they can honestly claim. 2–6 items, or empty array if none.

Return ONLY valid JSON with this schema (no markdown, no code fences). Escape double quotes in strings with backslash; do not escape apostrophes (e.g. write "candidate's" not "candidate\'s"). Do not use double quotes inside string values—rephrase or use apostrophes (e.g. "the candidate's experience" not "the \"best\" option"). Do not include literal newlines inside any string value; use a space or keep the sentence on one line.

{{
  "skills_to_consider_omitting": [
    {{ "skill": "<exact phrase from resume>", "reason": "<why for this job>", "priority": "cut_first" or "recommended" or "optional" }}
  ],
  "skills_to_consider_adding": [
    {{ "skill": "<skill name>", "reason": "<why for this job / where on resume>" }}
  ]
}}

If there are no suggestions for adding, use an empty array. For omitting, be THOROUGH but only from the TECHNICAL SKILLS block: list every skill in that block that is not clearly relevant to this job. Do not list skills that appear only in experience bullets.

JOB DESCRIPTION:
{job_text[:30000]}

RESUME:
{resume_text[:20000]}
""".strip()

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
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
