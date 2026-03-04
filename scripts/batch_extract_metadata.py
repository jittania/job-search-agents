"""
Fill or overwrite metadata:
- ✅ role title - works as expected
- ✅ company name - works as expected
- company type - ❌ seems to be defaulting incorrectly to "scale-up" or "unknown" in some cases
- company size bucket - ❌ having trouble with companies under < 1000
- role focus -  ❌ defaulting incorrectly to full-stack most of the time
- role level - ❌ defaulting incorrectly to mid
in the tracker sheet. Prompts: overwrite all or only populate rows missing metadata (company type empty).
Uses same job_dir logic as batchfitscore: job_dir/archive_path column or data/<company>/<date>.

Alias: batchmetadata
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import gspread
from anthropic import Anthropic
from dotenv import load_dotenv

DATA_DIR = Path("data")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEBUG_LOG_PATH = PROJECT_ROOT / ".cursor" / "debug-6857d3.log"

DATE_APPLIED_HEADER = "date applied"
JOB_DIR_HEADERS = ("job_dir", "archive_path", "archive path")

# Sheet column headers (case-insensitive) -> JSON key from extraction
METADATA_COLUMNS = {
    "company name": "company_name",
    "role title": "role_title",
    "company type": "company_type",
    "company size bucket": "company_size_bucket",
    "role focus": "role_focus",
    "role level": "role_level",
}

# Sentinel: if this column has a value, we consider the row to already have metadata (for "new only" mode)
METADATA_SENTINEL_HEADER = "company type"

# ---- Extraction (from job.txt + optional web search) ----
COMPANY_TYPES = ["STARTUP", "BIG TECH", "GOV", "SCALE-UP", "UNKNOWN"]
COMPANY_SIZE_BUCKETS = ["<50", "50-200", "200-1000", "1000+", "UNKNOWN"]
ROLE_FOCUS_OPTIONS = ["FRONTEND", "BACKEND", "FULL-STACK", "EMBEDDED", "ML"]
ROLE_LEVEL_OPTIONS = ["JUNIOR", "MID", "SENIOR", "STAFF", "PRINCIPAL"]
MAX_SEARCH_CHARS = 3500


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        payload = {"sessionId": "6857d3", "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data, "timestamp": int(time.time() * 1000)}
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _is_retryable(err: Exception) -> bool:
    s = str(err).lower()
    return "529" in s or "overloaded" in s or "429" in s or "rate" in s


def _derive_company_type_and_bucket(employee_count: int | None) -> tuple[str, str]:
    """Derive company_type and company_size_bucket from employee count. Hard rule: if employee count > 200, NEVER STARTUP."""
    if employee_count is None:
        return "UNKNOWN", "UNKNOWN"
    if employee_count < 50:
        return "STARTUP", "<50"
    if employee_count < 200:
        return "STARTUP", "50-200"
    if employee_count < 1000:
        return "SCALE-UP", "200-1000"
    return "SCALE-UP", "1000+"


def _company_display_name_from_slug(slug: str) -> str:
    """Turn folder slug into a search-friendly company name (e.g. anthropic -> Anthropic)."""
    if not slug or slug == "unknown":
        return ""
    return slug.replace("-", " ").title()


def _search_company_info(company_name: str) -> str:
    """Run web search for company size/type; return combined snippets or empty string on failure."""
    if not (company_name or "").strip():
        return ""
    try:
        from ddgs import DDGS
    except ImportError:
        return ""
    snippets = []
    queries = [
        f'"{company_name}" employee count',
        f'site:linkedin.com/company "{company_name}" employees',
        f'"{company_name}" headcount',
    ]
    try:
        ddgs = DDGS()
        for q in queries:
            try:
                results = ddgs.text(q, max_results=4)
                for r in results:
                    if isinstance(r, dict):
                        body = (r.get("body") or r.get("snippet") or "").strip()
                        title = (r.get("title") or "").strip()
                        if body:
                            snippets.append(f"[{title}] {body}")
                    elif hasattr(r, "body"):
                        snippets.append(getattr(r, "body", ""))
            except Exception:
                continue
    except Exception:
        return ""
    combined = "\n".join(snippets).strip()
    return combined[:MAX_SEARCH_CHARS] if combined else ""


def extract_metadata_for_job_dir(job_dir: Path) -> dict:
    """Extract role_title, company_type, company_size_bucket, role_focus, role_level from job_dir/job.txt. Uses optional web search for company size."""
    job_txt = job_dir / "job.txt"
    if not job_txt.exists():
        raise FileNotFoundError(f"No job.txt at {job_dir}")
    job_text = job_txt.read_text(encoding="utf-8")[:30000]

    company_slug = job_dir.parent.name
    company_display = _company_display_name_from_slug(company_slug)
    external_search = _search_company_info(company_display) if company_display else ""
    _debug_log("H3", "batch_extract_metadata:after_search", "external_search presence", {"company_slug": company_slug, "company_display": company_display, "search_len": len(external_search), "search_non_empty": bool(external_search.strip())})

    if external_search:
        search_block = f"""
EXTERNAL SEARCH RESULTS (use to set employee_count when a number is clearly stated; company_type and company_size_bucket will be derived from employee count):
{external_search}
"""
    else:
        search_block = "\n(No external search results available; use job posting only for employee_count if stated.)\n"

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""From the job posting below (and external search results when provided), extract metadata. Return ONLY valid JSON with exactly these keys:

- "company_name": string, the exact name of the company that is hiring (e.g. "Anthropic", "Google"). One line, no explanation. If unclear, "Unknown".
- "role_title": string, the exact job title from the posting (e.g. "Senior Software Engineer"). Use ONLY the job posting.
- "role_focus": exactly one of {json.dumps(ROLE_FOCUS_OPTIONS)}. Pick the SINGLE best match. Use FRONTEND only if the role is primarily front-end; BACKEND only if primarily back-end; FULL-STACK only if the posting explicitly says full-stack or clearly requires both. Do NOT default to FULL-STACK unless the posting clearly indicates it. Use EMBEDDED for firmware/hardware/embedded; ML for ML/MLOps/data-science focus.
- "role_level": exactly one of {json.dumps(ROLE_LEVEL_OPTIONS)}. Infer from job title and requirements. "Senior" or "Sr." in title → SENIOR; "Staff", "Principal", "Lead", "Architect" → STAFF or PRINCIPAL; "Junior", "Entry", "Graduate" → JUNIOR. Do NOT default to MID unless the posting clearly indicates mid-level; when in doubt prefer SENIOR if the title suggests it.
- "employee_count": integer or null. Set ONLY when a number is clearly stated in external search results or job posting (e.g. "50 employees", "headcount 200", "we're 500", "200+ employees"). Look in both the job posting and the search results. If unclear or absent, use null.
- "company_type": exactly one of {json.dumps(COMPANY_TYPES)}. Prefer from employee count when available: <200 → STARTUP; 200+ → SCALE-UP or BIG TECH. BIG TECH = well-known large tech (Google, Meta, Amazon, Microsoft, Apple, etc.). STARTUP = small, venture-backed, or early-stage. GOV = government/contractor. If employee count is stated and > 200, use SCALE-UP or BIG TECH, never STARTUP. If no clear signal, use UNKNOWN.
- "company_size_bucket": exactly one of {json.dumps(COMPANY_SIZE_BUCKETS)}. Prefer from employee count when stated: <50 → "<50", 50-199 → "50-200", 200-999 → "200-1000", 1000+ → "1000+". If employee count is not clearly stated, use UNKNOWN.

No other keys. No explanation.
{search_block}

JOB POSTING:
{job_text}
"""

    last_error = None
    msg = None
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except Exception as e:
            last_error = e
            if _is_retryable(e) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
    if msg is None:
        raise RuntimeError("Claude returned no message.")

    raw = (msg.content[0].text or "").strip()
    if not raw:
        raise RuntimeError("Claude returned empty output.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])

    _debug_log("H1_H4", "batch_extract_metadata:parsed_data", "LLM JSON keys and employee_count raw", {"data_keys": list(data.keys()), "employee_count_raw": data.get("employee_count"), "employee_count_type": type(data.get("employee_count")).__name__})

    def pick(allowed: list[str], key: str, default: str) -> str:
        val = (data.get(key) or "").strip()
        if not val:
            return default
        val_upper = val.upper().replace(" ", "")
        for a in allowed:
            if a.upper() == val.upper() or a.upper().replace(" ", "") in val_upper or val_upper in a.upper().replace(" ", ""):
                return a
        return default

    raw_ec = data.get("employee_count")
    employee_count: int | None = None
    if raw_ec is not None:
        if isinstance(raw_ec, int) and raw_ec > 0:
            employee_count = raw_ec
        elif isinstance(raw_ec, str) and raw_ec.strip():
            try:
                n = int(raw_ec.strip().replace(",", ""))
                if n > 0:
                    employee_count = n
            except ValueError:
                pass
    _debug_log("H2_H4", "batch_extract_metadata:after_parse_ec", "employee_count after parsing", {"raw_ec": raw_ec, "employee_count": employee_count})

    if employee_count is not None:
        company_type, company_size_bucket = _derive_company_type_and_bucket(employee_count)
        reason_company_type = f"derived from employee_count={employee_count}"
        reason_company_size = f"derived from employee_count={employee_count}"
    else:
        company_type = pick(COMPANY_TYPES, "company_type", "UNKNOWN")
        company_size_bucket = pick(COMPANY_SIZE_BUCKETS, "company_size_bucket", "UNKNOWN")
        reason_company_type = "from job posting (no employee_count found)"
        reason_company_size = "from job posting (no employee_count found)"
    _debug_log("H5", "batch_extract_metadata:derive_result", "company_type/size source", {"employee_count_in": employee_count, "company_type": company_type, "company_size_bucket": company_size_bucket, "source": "derived" if employee_count is not None else "llm_fallback"})

    role_focus = pick(ROLE_FOCUS_OPTIONS, "role_focus", "FULL-STACK")
    role_level = pick(ROLE_LEVEL_OPTIONS, "role_level", "SENIOR")

    reasons = {
        "company_type": reason_company_type,
        "company_size_bucket": reason_company_size,
        "role_focus": "from job posting",
        "role_level": "from job posting",
    }

    data_out = {
        "company_name": (data.get("company_name") or "").strip() or "Unknown",
        "role_title": (data.get("role_title") or "").strip() or "Unknown",
        "company_type": company_type,
        "company_size_bucket": company_size_bucket,
        "role_focus": role_focus,
        "role_level": role_level,
    }
    return data_out, reasons


def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def parse_date_applied(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    parts = raw.split("/")
    if len(parts) == 3:
        try:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100:
                dt = datetime(y, m, d)
                return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return None


def main():
    load_dotenv()

    sa_json = os.environ["GOOGLE_SA_JSON"]
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]

    gc = gspread.service_account(filename=sa_json)
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}

    company_col = col.get("company name") or col.get("company")
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    job_dir_col = next((col.get(h) for h in JOB_DIR_HEADERS if col.get(h)), None)
    sentinel_col = col.get(METADATA_SENTINEL_HEADER.lower())
    meta_cols = {header: col.get(header) for header in METADATA_COLUMNS}
    missing = [k for k, v in meta_cols.items() if not v]
    if missing:
        raise SystemExit(f"Sheet missing columns: {missing}")

    if not company_col:
        raise SystemExit('Sheet must have a column named "COMPANY NAME" (or "company").')
    if not date_applied_col:
        raise SystemExit(f'Sheet must have a column named "{DATE_APPLIED_HEADER}".')

    print("Metadata: overwrite all existing metadata, or only populate rows that don't have metadata yet?")
    choice = input("  [A]ll overwrite  |  [N]ew only (default: N): ").strip().upper() or "N"
    overwrite_all = choice == "A" or choice == "ALL"
    if overwrite_all:
        print("Mode: overwrite all existing metadata.\n")
    else:
        print("Mode: only populate rows missing metadata (company type empty).\n")

    rows = ws.get_all_values()[1:]

    for idx, row in enumerate(rows, start=2):
        company = (row[company_col - 1] or "").strip()
        date_applied_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        sentinel_val = (row[sentinel_col - 1] or "").strip() if sentinel_col and sentinel_col <= len(row) else ""

        if not company:
            continue
        if not overwrite_all and sentinel_val:
            continue

        date_iso = parse_date_applied(date_applied_raw)
        if not date_iso:
            print(f"Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        if job_dir_col and job_dir_col <= len(row):
            job_dir_val = (row[job_dir_col - 1] or "").strip()
            if job_dir_val:
                job_dir = (PROJECT_ROOT / job_dir_val).resolve() if not Path(job_dir_val).is_absolute() else Path(job_dir_val).resolve()
            else:
                job_dir = DATA_DIR / slugify(company) / date_iso
        else:
            job_dir = DATA_DIR / slugify(company) / date_iso
        job_txt = job_dir / "job.txt"
        if not job_txt.exists():
            print(f"Skipping row {idx}: no archived job at {job_dir}")
            continue

        print(f"Row {idx}: {company} | {date_iso}")

        try:
            data, reasons = extract_metadata_for_job_dir(job_dir)
        except Exception as e:
            print(f"  ⚠️ Failed: {e}")
            continue
        for header, json_key in METADATA_COLUMNS.items():
            c = meta_cols.get(header)
            if c and json_key in data:
                val = data.get(json_key)
                ws.update_cell(idx, c, val if val is not None else "")
        print(f"  → {data.get('company_name', '')} | {data.get('role_title', '')} | {data.get('company_type', '')} | {data.get('company_size_bucket', '')} | {data.get('role_focus', '')} | {data.get('role_level', '')}")
        print(f"     company_type: {reasons.get('company_type', '')}")
        print(f"     company_size_bucket: {reasons.get('company_size_bucket', '')}")
        print(f"     role_focus: {reasons.get('role_focus', '')}")
        print(f"     role_level: {reasons.get('role_level', '')}")

    print("\n✅ Done\n")


if __name__ == "__main__":
    main()
