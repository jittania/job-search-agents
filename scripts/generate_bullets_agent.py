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


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_bullets_agent.py <job_folder_path>")
        raise SystemExit(1)

    load_dotenv()

    job_dir = Path(sys.argv[1])
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

    # #region agent log
    _log_path = Path(".cursor/debug-6857d3.log")
    def _norm(s: str) -> str:
        return " ".join((s or "").split())
    def _word_count(s: str) -> int:
        return len((s or "").split())
    try:
        bullets_remove = data.get("bullets_to_remove") or []
        tailored = data.get("tailored_bullets") or []
        n_replace = sum(1 for t in tailored if (t.get("placement") or {}).get("action") == "replace")
        n_append = len(tailored) - n_replace
        resume_lines = resume_text.splitlines()
        all_bullet_texts = []
        for line in resume_lines:
            stripped = line.strip()
            if stripped.startswith("*"):
                bullet_text = stripped.lstrip("*").strip()
                all_bullet_texts.append(bullet_text)
        replace_refs = [((t.get("placement") or {}).get("replace_bullet_index") or "").strip() for t in tailored if (t.get("placement") or {}).get("action") == "replace"]
        remove_refs = [(r.get("bullet_index") or "").strip() for r in bullets_remove if isinstance(r.get("bullet_index"), str) and (r.get("bullet_index") or "").strip()]
        replace_match_1 = sum(1 for ref in replace_refs if ref and sum(1 for bt in all_bullet_texts if _norm(ref) == _norm(bt)) == 1)
        replace_match_0 = sum(1 for ref in replace_refs if ref and sum(1 for bt in all_bullet_texts if _norm(ref) == _norm(bt)) == 0)
        remove_match_1 = sum(1 for ref in remove_refs if ref and sum(1 for bt in all_bullet_texts if _norm(ref) == _norm(bt)) == 1)
        remove_match_0 = sum(1 for ref in remove_refs if ref and sum(1 for bt in all_bullet_texts if _norm(ref) == _norm(bt)) == 0)
        new_wc = sum(_word_count(t.get("bullet") or "") for t in tailored)
        old_wc = 0
        for t in tailored:
            if (t.get("placement") or {}).get("action") != "replace":
                continue
            ref = ((t.get("placement") or {}).get("replace_bullet_index") or "").strip()
            if not ref:
                continue
            for bt in all_bullet_texts:
                if _norm(ref) == _norm(bt):
                    old_wc += _word_count(bt)
                    break
        with open(_log_path, "a", encoding="utf-8") as _f:
            import time as _time
            _f.write(json.dumps({"sessionId": "6857d3", "hypothesisId": "H1", "location": "generate_bullets_agent.py", "message": "genbullets counts", "data": {"bullets_to_remove": len(bullets_remove), "tailored_bullets": len(tailored), "n_replace": n_replace, "n_append": n_append, "ratio_remove_to_replace": round(len(bullets_remove) / max(n_replace, 1), 2)}, "timestamp": int(_time.time() * 1000)}) + "\n")
            _f.write(json.dumps({"sessionId": "6857d3", "hypothesisId": "H3", "location": "generate_bullets_agent.py", "message": "replace/remove ref match (full bullet)", "data": {"replace_match_exactly_one": replace_match_1, "replace_match_zero": replace_match_0, "remove_match_exactly_one": remove_match_1, "remove_match_zero": remove_match_0}, "timestamp": int(_time.time() * 1000)}) + "\n")
            _f.write(json.dumps({"sessionId": "6857d3", "hypothesisId": "H4", "location": "generate_bullets_agent.py", "message": "word count new vs old", "data": {"new_bullets_total_words": new_wc, "replaced_old_bullets_total_words": old_wc, "net_word_delta": new_wc - old_wc}, "timestamp": int(_time.time() * 1000)}) + "\n")
    except Exception as _e:
        try:
            with open(_log_path, "a", encoding="utf-8") as _f:
                import time as _time
                _f.write(json.dumps({"sessionId": "6857d3", "hypothesisId": "H1,H3,H4", "location": "generate_bullets_agent.py", "message": "genbullets log error", "data": {"error": str(_e)}, "timestamp": int(_time.time() * 1000)}) + "\n")
        except Exception:
            pass
    # #endregion

    out_path = job_dir / "resume_bullets.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📝 Wrote {out_path}\n")


if __name__ == "__main__":
    main()