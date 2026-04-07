"""
Populate a cover letter for a single job folder. Writes cover_letter.md (overwrites if present, same as genbullets).

Invoked by: popcl (batch). Single job: popcl data/<company>/<date> or popcl <company_slug> (same as genbullets).
"""
import os
import re
import sys
from pathlib import Path

from anthropic import Anthropic, AnthropicError
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent

COVER_LETTER_MODEL = "claude-sonnet-4-6"
MAX_TOKENS_DRAFT = 900
MAX_TOKENS_VALIDATION = 1200


def _strip_letter_markdown_fences(text: str) -> str:
    text = (text or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_validated_letter(raw: str) -> str:
    text = _strip_letter_markdown_fences(raw)
    if not text:
        raise ValueError("empty letter after stripping fences")
    if len(text) < 80:
        raise ValueError("letter too short to be valid")
    return text


def _cover_letter_validation_prompt(job_text: str, resume_text: str, draft_letter: str) -> str:
    return f"""
You are a strict editor validating a cover letter draft against the candidate's resume only.

You have the JOB DESCRIPTION (context only — do not add claims from it unless the same fact appears on the resume), the full RESUME (verbatim — sole source of truth), and the DRAFT LETTER.

Your job: return a CORRECTED version of the letter in plain text. Preserve tone, length (roughly 220–320 words), and at most 3 paragraphs unless the draft must be split to fix duplication. Apply ALL rules below. If the draft is already compliant, return it unchanged.

Rules:
1) Technologies and responsibilities: Remove or rephrase any technology, tool, framework, or responsibility that does not appear verbatim (or as an unambiguous exact synonym of a phrase) on the resume. Do not infer skills from the job description.
2) Accomplishment accuracy: Remove or soften any accomplishment or scope claim that overstates the resume (e.g. team-wide, org-wide, "influenced practices," "led initiative" unless the resume explicitly supports that scope). Prefer claims that match individual contribution as written.
3) Years of experience: Remove or fix any "X years" or tenure claim that does not match dates or wording on the resume.
4) Duplicate openers: No two paragraphs may start with the same opening phrase or structural pattern (e.g. both starting with "In my role…"). Reword so each paragraph opens distinctly.

Output rules:
- Plain text only: the full corrected letter, nothing else.
- No preamble or meta (e.g. do not start with "Here is…" or "Below is…").
- Start directly with the first sentence of the letter.

JOB DESCRIPTION (context):
{job_text}

RESUME:
{resume_text}

DRAFT LETTER:
{draft_letter}
""".strip()


def run_cover_letter_validation_pass(
    client: Anthropic,
    job_text: str,
    resume_text: str,
    draft_letter: str,
    model: str,
    max_tokens: int,
) -> tuple[str, int]:
    """Returns (validated_letter, output_tokens). Retries once on parse failure."""
    prompt = _cover_letter_validation_prompt(job_text, resume_text, draft_letter)
    output_tokens = 0
    for attempt in range(2):
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        output_tokens = msg.usage.output_tokens
        raw = (msg.content[0].text or "").strip()
        try:
            letter = _parse_validated_letter(raw)
            break
        except ValueError as e:
            if attempt == 0:
                print("  Validation pass: parse failed, retrying once…", file=sys.stderr)
                prompt = prompt + "\n\nImportant: Reply with ONLY the final cover letter as plain text. No markdown fences, no title, no commentary."
            else:
                print(f"Validation pass parse error: {e}", file=sys.stderr)
                raise SystemExit(1)
    return letter, output_tokens


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/populate_cover_letter_agent.py <job_folder|company_slug>",
            file=sys.stderr,
        )
        raise SystemExit(1)

    sys.path.insert(0, str(SCRIPT_DIR))
    from generate_bullets_agent import resolve_job_dir

    try:
        job_dir = resolve_job_dir(sys.argv[1])
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    job_txt = job_dir / "job.txt"
    url_txt = job_dir / "url.txt"
    out_path = job_dir / "cover_letter.md"

    if not job_txt.exists():
        raise SystemExit("Missing job.txt")

    load_dotenv()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resume_loader import get_resume_text
    try:
        resume_text = get_resume_text()
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print("Set ANTHROPIC_API_KEY in .env or your environment.", file=sys.stderr)
        raise SystemExit(1)

    client = Anthropic(api_key=api_key)

    job_text = job_txt.read_text(encoding="utf-8")
    url = url_txt.read_text(encoding="utf-8").strip() if url_txt.exists() else ""

    prompt = f"""
        Write a concise, confident cover letter tailored to this job.

        CRITICAL — Only reference experience and technologies that appear on the resume. Do not mention any technologies, tools, or responsibilities from the job description unless they explicitly appear on the resume. If the JD asks for something the resume does not show, do not claim it—emphasize the candidate's actual skills and experience instead.

        Constraints:
        - 220–320 words
        - 3 short paragraphs max
        - No buzzword soup
        - No claims you can't support from the resume; only mention tech and experience that is on the resume
        - Reference the company/role naturally (if the JD provides it)
        - End with a simple call to action
        - Output plain text ONLY. Do not include any introductory or meta sentence (e.g. "Here is a cover letter tailored to..."); start directly with the first paragraph of the letter.

        JOB POSTING URL (if available):
        {url}

        JOB DESCRIPTION:
        {job_text}

        RESUME:
        {resume_text}
        """.strip()

    try:
        msg = client.messages.create(
            model=COVER_LETTER_MODEL,
            max_tokens=MAX_TOKENS_DRAFT,
            messages=[{"role": "user", "content": prompt}],
        )
        print(f"🪙 Draft output tokens: {msg.usage.output_tokens}", file=sys.stderr)
    except AnthropicError as e:
        print(f"Anthropic API error: {e}", file=sys.stderr)
        raise SystemExit(1)

    draft = (msg.content[0].text or "").strip()
    if not draft:
        raise SystemExit("Model returned empty output")

    draft = re.sub(
        r"^Here is (a |an )?(concise,? )?(confident,? )?cover letter (tailored to|for) .+?[.:]\s*\n*",
        "",
        draft,
        flags=re.IGNORECASE,
    ).strip()

    try:
        letter, val_tokens = run_cover_letter_validation_pass(
            client,
            job_text,
            resume_text,
            draft,
            model=COVER_LETTER_MODEL,
            max_tokens=MAX_TOKENS_VALIDATION,
        )
        print(f"🪙 Validation output tokens: {val_tokens}", file=sys.stderr)
    except AnthropicError as e:
        print(f"Anthropic API error (validation): {e}", file=sys.stderr)
        raise SystemExit(1)

    letter = re.sub(
        r"^Here is (a |an )?(concise,? )?(confident,? )?cover letter (tailored to|for) .+?[.:]\s*\n*",
        "",
        letter,
        flags=re.IGNORECASE,
    ).strip()

    try:
        out_path.write_text(letter + "\n", encoding="utf-8")
    except OSError as e:
        print(f"Could not write {out_path}: {e}", file=sys.stderr)
        raise SystemExit(1)

    print(f"\n✍️ Wrote {out_path}\n")


if __name__ == "__main__":
    main()