"""
Score a single job 0-100 from structured extraction + deterministic (rules-based) subscores.
LLM extracts must_have/nice_to_have; Python computes subscores and penalties. Reads job_dir/job.txt
and resume from path; fails if missing or too short. Outputs JSON: subscores, penalties, total,
must_have_missing, hard_gates_triggered.

Invoked by: popjobs, batchfitscore (no direct alias).
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

# Deterministic fit scoring constants
DOMAIN_FOCUS_VALUES = frozenset({
    "product-web", "infra", "data", "healthcare-integration", "embedded", "other"
})
REQUIREMENT_SYNONYMS = {
    "net": {"net", "aspnet", "dotnet"},
    "aspnet": {"net", "aspnet", "dotnet"},
    "dotnet": {"net", "aspnet", "dotnet"},
    "c#": {"c#", "csharp"},
    "csharp": {"c#", "csharp"},
    "graphql": {"graphql", "apollo"},
    "apollo": {"graphql", "apollo"},
    "k8s": {"k8s", "kubernetes"},
    "kubernetes": {"k8s", "kubernetes"},
    "ga": {"ga", "google analytics"},
    "google analytics": {"ga", "google analytics"},
    "bigquery": {"bigquery", "gcp bigquery"},
    "gcp bigquery": {"bigquery", "gcp bigquery"},
    "java ee": {"java ee", "j2ee", "jee", "servlet", "jsp"},
    "j2ee": {"java ee", "j2ee", "jee", "servlet", "jsp"},
    "servlet": {"java ee", "servlet", "jsp"},
    "jsp": {"java ee", "servlet", "jsp"},
    "windows server": {"windows server", "win server"},
    "hl7": {"hl7"},
    "go": {"go", "golang"},
    "golang": {"go", "golang"},
}
HARD_REQUIRED_TECH_PATTERNS = [
    ("c#", 25), (".net", 25), ("asp.net", 25), ("graphql", 25), ("hl7", 35),
    ("go", 25), ("golang", 25), ("java ee", 25), ("j2ee", 25), ("jsp", 25),
    ("servlet", 25), ("windows server", 25),
]
SENIORITY_CAP_YEARS_GAP = 3
SENIORITY_CAP_MAX_TOTAL = 55
# Bigger experience-gap penalty so overly senior roles are ruled out earlier.
SENIORITY_GAP_PENALTY_BASE = 15
SENIORITY_GAP_PENALTY_PER_YEAR = 10
SENIORITY_GAP_PENALTY_MAX = 45
TWO_PLUS_REQUIRED_MISSING_CAP = 55

EXIT_SECURITY_CLEARANCE = 3
MIN_JOB_CHARS = 500
MIN_RESUME_CHARS = 500

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def _hash_content(text: str, max_chars: int = 10000) -> str:
    return hashlib.sha256((text or "")[:max_chars].encode("utf-8")).hexdigest()[:16]


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", (s or "").lower()).strip()


def _normalize_text_for_substring(text: str) -> str:
    if not text:
        return ""
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9#]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _requirement_appears_in_text(req: str, normalized_text: str) -> bool:
    if not normalized_text or not (req or "").strip():
        return False
    words = _normalize(req).split()
    for w in words:
        if len(w) < 2:
            continue
        equiv = REQUIREMENT_SYNONYMS.get(w, {w})
        for token in equiv:
            if token in normalized_text:
                return True
    norm_req = _normalize(req)
    if norm_req and norm_req in normalized_text:
        return True
    return False


def _requirement_appears_in_resume_text(req: str, normalized_resume_text: str) -> bool:
    return _requirement_appears_in_text(req, normalized_resume_text)


def _requirement_appears_in_job_text(req: str, normalized_job_text: str) -> bool:
    return _requirement_appears_in_text(req, normalized_job_text)


def _validate_must_have_against_job_text(
    must_have: list[str], normalized_job_text: str
) -> tuple[list[str], list[str]]:
    kept = []
    dropped = []
    for item in must_have:
        s = (item or "").strip()
        if not s:
            continue
        if _requirement_appears_in_job_text(s, normalized_job_text):
            kept.append(s)
        else:
            dropped.append(s)
    return kept, dropped


def _state_claims_dotnet_core(must_have: list, dropped: list) -> bool:
    for item in (must_have or []) + (dropped or []):
        n = _normalize(str(item))
        if "net" in n and "core" in n:
            return True
    return False


def _show_dotnet_core_in_job_text_or_skip_fail(job_text: str) -> bool:
    t = job_text.lower()
    for phrase in (".net core", "net core"):
        i = t.find(phrase)
        if i != -1:
            start = max(0, i - 80)
            end = min(len(job_text), i + len(phrase) + 80)
            print(f"[fit-score] assertion: job_text contains {phrase!r} at index {i}; substring: {job_text[start:end]!r}", file=sys.stderr)
            return True
    return False


def _resume_match_set(resume_struct: dict) -> set:
    out = set()
    for key in ("skills", "languages_frameworks", "databases_cloud_tools", "keywords"):
        for item in (resume_struct.get(key) or []):
            if not isinstance(item, str) or not item.strip():
                continue
            norm = _normalize(item)
            out.add(norm)
            for word in norm.split():
                if len(word) >= 2:
                    out.add(word)
    expanded = set(out)
    for t in out:
        for k, v in REQUIREMENT_SYNONYMS.items():
            if t in v or t == k:
                expanded.add(k)
                expanded.update(v)
    return expanded


def _is_hard_required_tech(requirement: str) -> tuple[bool, int]:
    r = _normalize(requirement)
    words = set(r.split())
    for pattern, penalty in HARD_REQUIRED_TECH_PATTERNS:
        p = _normalize(pattern)
        if p in r or p in words:
            return True, penalty
    return False, 0


def _must_have_matches(
    job_struct: dict,
    resume_struct: dict,
    normalized_resume_text: str,
) -> tuple[list[str], list[str], list[tuple[str, int]], list[str]]:
    must_have = [str(x).strip() for x in (job_struct.get("must_have") or []) if x]
    matched = []
    missing = []
    hard_missing: list[tuple[str, int]] = []
    hard_gates_triggered: list[str] = []

    for req in must_have:
        if _requirement_appears_in_resume_text(req, normalized_resume_text):
            matched.append(req)
        else:
            missing.append(req)
            is_hard, penalty = _is_hard_required_tech(req)
            if is_hard:
                hard_missing.append((req, penalty))
                hard_gates_triggered.append(f"Missing required tech/cert: {req[:60]} (-{penalty})")

    return matched, missing, hard_missing, hard_gates_triggered


def _score_deterministic(job_struct: dict, resume_struct: dict, normalized_resume_text: str) -> dict:
    matched_must, must_have_missing, hard_missing_with_penalty, hard_gates_triggered = _must_have_matches(
        job_struct, resume_struct, normalized_resume_text
    )
    must_have = [str(x).strip() for x in (job_struct.get("must_have") or []) if x]
    nice_to_have = [str(x).strip() for x in (job_struct.get("nice_to_have") or []) if x]
    resume_tokens = _resume_match_set(resume_struct)
    seniority_req = job_struct.get("seniority_years_required")
    if seniority_req is not None and isinstance(seniority_req, (int, float)):
        seniority_req = int(round(float(seniority_req)))
    years_est = resume_struct.get("years_experience_estimate")
    if years_est is not None and isinstance(years_est, (int, float)):
        years_est = float(years_est)
    domain_focus = (job_struct.get("domain_focus") or "other").strip().lower()
    if domain_focus not in DOMAIN_FOCUS_VALUES:
        domain_focus = "other"

    if not must_have:
        core_stack = 60
    else:
        core_stack = int(round(60 * len(matched_must) / len(must_have)))
    nice_matched = sum(
        1 for n in nice_to_have
        if _requirement_appears_in_resume_text(n, normalized_resume_text)
    )
    if nice_to_have and core_stack < 60:
        core_stack = min(60, core_stack + min(5, 2 * nice_matched))
    core_stack = max(0, min(60, core_stack))

    if seniority_req is None:
        level = 20
    elif years_est is None:
        level = 10
    elif years_est >= seniority_req:
        level = 20
    elif years_est >= seniority_req - 1:
        level = 14
    elif years_est >= seniority_req - 2:
        level = 8
    else:
        level = 2
    level = max(0, min(20, level))

    kw_lower = " ".join(resume_tokens)
    if domain_focus == "product-web" and ("react" in kw_lower or "frontend" in kw_lower or "web" in kw_lower or "typescript" in kw_lower):
        domain = 10
    elif domain_focus == "healthcare-integration" and ("hl7" in kw_lower or "healthcare" in kw_lower or "integration" in kw_lower):
        domain = 10
    elif domain_focus == "infra" and ("aws" in kw_lower or "kubernetes" in kw_lower or "k8s" in kw_lower or "docker" in kw_lower or "cloud" in kw_lower):
        domain = 10
    elif domain_focus == "data" and ("sql" in kw_lower or "data" in kw_lower or "etl" in kw_lower):
        domain = 10
    elif domain_focus == "embedded":
        domain = 7 if "embedded" in kw_lower or "c++" in kw_lower or "rust" in kw_lower else 3
    else:
        domain = 7
    domain = max(0, min(10, domain))
    logistics = 10

    penalties = []
    for req, penalty in hard_missing_with_penalty:
        penalties.append({"reason": f"Missing required (hard gate): {req[:70]}", "points": penalty})
    generic_missing = [r for r in must_have_missing if not any(r == h[0] for h in hard_missing_with_penalty)]
    for req in generic_missing:
        penalties.append({"reason": f"Missing required: {req[:70]}", "points": 12})

    if seniority_req is not None and years_est is not None and years_est < seniority_req - 1:
        gap = seniority_req - years_est
        if gap >= 2:
            pt = min(SENIORITY_GAP_PENALTY_MAX, SENIORITY_GAP_PENALTY_BASE + SENIORITY_GAP_PENALTY_PER_YEAR * int(gap))
            penalties.append({"reason": f"Level gap: {seniority_req}+ years required, ~{years_est} on resume", "points": pt})
            if gap >= SENIORITY_CAP_YEARS_GAP:
                hard_gates_triggered.append(f"Seniority gap {gap} years (required {seniority_req}+, resume ~{years_est}) -> cap total at {SENIORITY_CAP_MAX_TOTAL}")

    total = core_stack + level + domain + logistics - sum(p["points"] for p in penalties)
    total = max(0, min(100, total))

    if len(hard_missing_with_penalty) >= 2:
        total = min(total, TWO_PLUS_REQUIRED_MISSING_CAP)
        hard_gates_triggered.append(f"2+ required tech/cert missing -> cap total at {TWO_PLUS_REQUIRED_MISSING_CAP}")
    if seniority_req is not None and years_est is not None and (seniority_req - years_est) >= SENIORITY_CAP_YEARS_GAP:
        total = min(total, SENIORITY_CAP_MAX_TOTAL)

    return {
        "subscores": {"core_stack": core_stack, "level": level, "domain": domain, "logistics": logistics},
        "penalties": penalties,
        "total": total,
        "must_have_missing": must_have_missing,
        "must_have_matched": matched_must,
        "hard_gates_triggered": hard_gates_triggered,
    }


def _parse_job_extraction_response(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError("No JSON in job extraction output.")
    data = json.loads(raw[start : end + 1])
    if "must_have" not in data:
        data["must_have"] = []
    if "nice_to_have" not in data:
        data["nice_to_have"] = []
    if "domain_focus" not in data or data["domain_focus"] not in DOMAIN_FOCUS_VALUES:
        data["domain_focus"] = "other"
    return data


def _extract_job_requirements(client: Anthropic, job_text: str, verbatim_only: bool = False) -> dict:
    if verbatim_only:
        prompt = f"""Extract requirements from this job description. Return ONLY valid JSON with this exact schema (no other fields):
{{
  "must_have": ["item1", "item2"],
  "nice_to_have": ["item1"],
  "seniority_years_required": 3,
  "domain_focus": "product-web"
}}

CRITICAL: For must_have, only copy phrases that appear verbatim (or near-verbatim, e.g. "C#" or ".NET") in the job description. Do NOT infer, paraphrase, or add requirements that are not explicitly written in the text.

JOB DESCRIPTION:
{job_text[:30000]}
"""
    else:
        prompt = f"""Extract ONLY explicitly stated requirements from this job description. Return ONLY valid JSON with this exact schema (no other fields):
{{
  "must_have": ["item1", "item2"],
  "nice_to_have": ["item1"],
  "seniority_years_required": 3,
  "domain_focus": "product-web"
}}

Rules: must_have: ONLY skills/tech/experience explicitly stated as REQUIRED. nice_to_have: preferred. seniority_years_required: number if stated, else null. domain_focus: exactly one of product-web, infra, data, healthcare-integration, embedded, other.

JOB DESCRIPTION:
{job_text[:30000]}
"""
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt.strip()}],
    )
    raw_out = (msg.content[0].text or "").strip()
    return _parse_job_extraction_response(raw_out)


def _extract_resume_evidence(client: Anthropic, resume_text: str) -> dict:
    prompt = f"""Extract structured evidence from this resume. Return ONLY valid JSON with this exact schema (no other fields):
{{
  "skills": ["skill1", "skill2"],
  "languages_frameworks": ["React", "Python"],
  "databases_cloud_tools": ["AWS", "PostgreSQL"],
  "years_experience_estimate": 2.5,
  "keywords": ["keyword1", "keyword2"]
}}
List only stated technologies and skills. years_experience_estimate from employment dates.

RESUME:
{resume_text[:15000]}
"""
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt.strip()}],
    )
    raw = (msg.content[0].text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError("No JSON in resume extraction output.")
    data = json.loads(raw[start : end + 1])
    for key in ("skills", "languages_frameworks", "databases_cloud_tools", "keywords"):
        if key not in data or not isinstance(data[key], list):
            data[key] = []
    data["years_experience_estimate"] = data.get("years_experience_estimate")
    return data


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/initial_fit_score_agent.py <job_folder_path> [resume_path]", file=sys.stderr)
        raise SystemExit(1)

    load_dotenv()

    job_dir = Path(sys.argv[1]).resolve()
    job_txt = job_dir / "job.txt"
    if not job_txt.exists():
        print(f"Missing job file: {job_txt}", file=sys.stderr)
        raise SystemExit(2)

    job_text = job_txt.read_text(encoding="utf-8")

    if len(sys.argv) >= 3:
        resume_path = Path(sys.argv[2]).resolve()
        if not resume_path.exists():
            print(f"Missing resume file: {resume_path}", file=sys.stderr)
            raise SystemExit(2)
        resume_text = resume_path.read_text(encoding="utf-8")
    else:
        sys.path.insert(0, str(SCRIPT_DIR))
        try:
            from resume_loader import get_resume_text
            resume_text = get_resume_text()
        except FileNotFoundError as e:
            print(f"Resume: {e}", file=sys.stderr)
            raise SystemExit(2)
        resume_path = None

    if len(job_text) < MIN_JOB_CHARS:
        print(f"FAIL: Job text too short: {len(job_text)} chars (min {MIN_JOB_CHARS}). Do not write score.", file=sys.stderr)
        raise SystemExit(2)
    if len(resume_text) < MIN_RESUME_CHARS:
        print(f"FAIL: Resume text too short: {len(resume_text)} chars (min {MIN_RESUME_CHARS}). Do not write score.", file=sys.stderr)
        raise SystemExit(2)

    job_hash = _hash_content(job_text)
    resume_hash = _hash_content(resume_text)
    print(f"[fit-score] job_path={job_txt.resolve()!r} job_hash={job_hash}", file=sys.stderr)
    resume_path_str = resume_path.resolve() if resume_path else "Google Doc or default file"
    print(f"[fit-score] resume_path={resume_path_str!r} resume_hash={resume_hash}", file=sys.stderr)
    print(f"[fit-score] job_text (first 300 chars): {job_text[:300]!r}", file=sys.stderr)
    print(f"[fit-score] resume_text (first 300 chars): {resume_text[:300]!r}", file=sys.stderr)

    sys.path.insert(0, str(SCRIPT_DIR))
    from check_security_clearance import requires_security_clearance
    if requires_security_clearance(job_dir):
        print("SECURITY_CLEARANCE_REQUIRED", file=sys.stderr)
        raise SystemExit(EXIT_SECURITY_CLEARANCE)

    company_slug = job_dir.parent.name
    date_iso = job_dir.name

    normalized_job_text = _normalize_text_for_substring(job_text)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    job_struct = _extract_job_requirements(client, job_text)
    resume_struct = _extract_resume_evidence(client, resume_text)

    original_must_have = [str(x).strip() for x in (job_struct.get("must_have") or []) if x]
    kept_must_have, dropped = _validate_must_have_against_job_text(original_must_have, normalized_job_text)
    job_struct["must_have"] = kept_must_have
    job_struct["dropped_requirements_not_in_job_text"] = dropped
    if dropped:
        print(f"[fit-score] dropped_requirements_not_in_job_text: {dropped!r}", file=sys.stderr)

    if original_must_have and len(dropped) > len(original_must_have) * 0.5:
        job_struct_retry = _extract_job_requirements(client, job_text, verbatim_only=True)
        orig_retry = [str(x).strip() for x in (job_struct_retry.get("must_have") or []) if x]
        kept_retry, dropped_retry = _validate_must_have_against_job_text(orig_retry, normalized_job_text)
        if orig_retry and len(dropped_retry) <= len(orig_retry) * 0.5:
            job_struct["must_have"] = kept_retry
            job_struct["dropped_requirements_not_in_job_text"] = dropped_retry
            if dropped_retry:
                print(f"[fit-score] after strict retry, dropped_requirements_not_in_job_text: {dropped_retry!r}", file=sys.stderr)
        elif orig_retry and len(dropped_retry) > len(orig_retry) * 0.5:
            if _state_claims_dotnet_core(kept_retry, dropped_retry) and not _show_dotnet_core_in_job_text_or_skip_fail(job_text):
                pass
            else:
                print("FAIL: Extraction unreliable. More than 50% of must_have items could not be verified in job text after strict retry. Do not write score.", file=sys.stderr)
                raise SystemExit(2)

    job_first300 = job_text[:300].lower()
    expected_slug = company_slug.lower()
    expected_with_spaces = company_slug.replace("-", " ").lower()
    if expected_slug not in job_first300 and expected_with_spaces not in job_first300:
        print(f"FAIL: Expected company name (e.g. {company_slug!r}) not found in first 300 chars of job text; likely wrong job file. Do not write score.", file=sys.stderr)
        raise SystemExit(2)

    normalized_resume_text = _normalize_text_for_substring(resume_text)
    result = _score_deterministic(job_struct, resume_struct, normalized_resume_text)

    must_have_all = [str(x).strip() for x in (job_struct.get("must_have") or []) if x]
    dropped_list = job_struct.get("dropped_requirements_not_in_job_text") or []
    out = {
        "company": company_slug,
        "date": date_iso,
        "job_hash": job_hash,
        "resume_hash": resume_hash,
        "subscores": result["subscores"],
        "penalties": result["penalties"],
        "total": result["total"],
        "must_have_missing": result["must_have_missing"],
        "hard_gates_triggered": result["hard_gates_triggered"],
        "dropped_requirements_not_in_job_text": dropped_list,
        "must_have_sample": must_have_all[:5],
        "matched_resume_sample": result["must_have_matched"][:5],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
