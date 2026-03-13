"""
Fill or overwrite initial fit score (0-100) in the tracker sheet. Prompts: overwrite all or only
populate rows missing a score. Runs initial_fit_score_agent per row; writes total. Optional
job_dir/archive_path column for row→job mapping. Safeguard: stops if same total repeats 3 rows in a row.

Alias: batchfitscore
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

INITIAL_FIT_SCRIPT = Path(__file__).resolve().parent / "initial_fit_score_agent.py"
DATA_DIR = Path("data")
PROJECT_ROOT = Path(__file__).resolve().parent.parent

INITIAL_FIT_SCORE_HEADER = "initial fit score"
DATE_APPLIED_HEADER = "date applied"
# Optional: if sheet has job_dir or archive_path column, use that for row→job mapping (unique dir per job).
JOB_DIR_HEADERS = ("job_dir", "archive_path", "archive path")

# Safeguard: stop if this many consecutive rows have the same total
REPEAT_TOTAL_THRESHOLD = 3


def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def parse_date_applied(raw: str) -> str | None:
    """Parse date applied from sheet into YYYY-MM-DD, or return None if missing/invalid."""
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


def log_top5(job_label: str, data: dict) -> None:
    """Log must_have_sample, matched, must_have_missing, hard_gates_triggered to stderr (for debugging)."""
    must = data.get("must_have_sample") or []
    matched = data.get("matched_resume_sample") or []
    missing = data.get("must_have_missing") or []
    hard_gates = data.get("hard_gates_triggered") or []
    print(f"  [log] {job_label} — top 5 must_have: {must[:5]!r}", file=sys.stderr)
    print(f"  [log] {job_label} — top 5 matched: {matched[:5]!r}", file=sys.stderr)
    if missing:
        print(f"  [log] {job_label} — must_have_missing: {missing[:10]!r}", file=sys.stderr)
    if hard_gates:
        print(f"  [log] {job_label} — hard_gates_triggered: {hard_gates!r}", file=sys.stderr)


# Value written to fit score column when user chooses "skip" after a failure
FIT_SCORE_ERROR_VALUE = "Error"


def prompt_on_failure(ws, row_idx: int, initial_fit_col: int, reason: str) -> None:
    """On agent/parse failure: print reason, ask skip vs continue; if skip, write Error to sheet."""
    print(f"\n⚠️ Failed (row {row_idx}):\n{reason}\n")
    choice = input(
        "  [S]kip (write 'Error' in fit score and continue)  |  [C]ontinue (leave cell unchanged and continue): "
    ).strip().upper() or "C"
    if choice in ("S", "SKIP"):
        ws.update_cell(row_idx, initial_fit_col, FIT_SCORE_ERROR_VALUE)
        print(f"  → Wrote '{FIT_SCORE_ERROR_VALUE}' to row {row_idx}; continuing.\n")


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
    initial_fit_col = col.get(INITIAL_FIT_SCORE_HEADER.lower())
    job_dir_col = next((col.get(h) for h in JOB_DIR_HEADERS if col.get(h)), None)

    if not company_col:
        raise SystemExit('Sheet must have a column named "COMPANY NAME" (or "company").')
    if not date_applied_col:
        raise SystemExit(f'Sheet must have a column named "{DATE_APPLIED_HEADER}".')
    if not initial_fit_col:
        raise SystemExit(f'Sheet must have a column named "{INITIAL_FIT_SCORE_HEADER}".')

    company_filter = (sys.argv[1].strip() if len(sys.argv) > 1 else None) or None
    if company_filter:
        print(f"Company filter: only rows matching {company_filter!r}\n")
        overwrite_all = True
    else:
        print("Initial fit score: overwrite all existing scores, or only populate rows that don't have a score yet?")
        choice = input("  [A]ll overwrite  |  [N]ew only (default: N): ").strip().upper() or "N"
        overwrite_all = choice == "A" or choice == "ALL"
    if overwrite_all:
        print("Mode: overwrite all existing fit scores.\n")
    elif not company_filter:
        print("Mode: only populate rows missing a score.\n")

    rows = ws.get_all_values()[1:]
    last_totals: list[int] = []
    first_resume_hash: str | None = None

    for idx, row in enumerate(rows, start=2):
        company = (row[company_col - 1] or "").strip()
        date_applied_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        initial_fit_val = (row[initial_fit_col - 1] or "").strip() if initial_fit_col <= len(row) else ""

        if not company:
            continue
        if company_filter and company_filter.lower() not in company.lower() and slugify(company) != slugify(company_filter):
            continue
        if not overwrite_all and initial_fit_val:
            continue

        date_iso = parse_date_applied(date_applied_raw)
        if not date_iso:
            print(f"\n⏭️ Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        # Prefer explicit job_dir/archive_path from sheet (unique dir per job); else derive from company+date
        job_dir_val = ""
        if job_dir_col and job_dir_col <= len(row):
            job_dir_val = (row[job_dir_col - 1] or "").strip()
        if job_dir_val:
            job_dir = (PROJECT_ROOT / job_dir_val).resolve() if not Path(job_dir_val).is_absolute() else Path(job_dir_val).resolve()
        else:
            job_dir = DATA_DIR / slugify(company) / date_iso
        job_txt = job_dir / "job.txt"
        if not job_txt.exists():
            print(f"\n⏭️ Skipping row {idx}: no archived job at {job_dir}")
            continue

        print(f"\nScoring row {idx}: {company} | {date_iso}")

        result = subprocess.run(
            ["python", str(INITIAL_FIT_SCRIPT), str(job_dir)],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parent.parent,
        )

        if result.returncode == 3 or "SECURITY_CLEARANCE_REQUIRED" in (result.stderr or ""):
            print("  ⏭️ Skipped (security clearance required)")
            if initial_fit_col:
                ws.update_cell(idx, initial_fit_col, "N/A (clearance)")
            continue
        if result.returncode != 0:
            reason = (result.stderr or result.stdout or "Unknown error").strip()
            prompt_on_failure(ws, idx, initial_fit_col, reason)
            continue

        stdout = result.stdout.strip()
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            reason = f"Invalid JSON from agent: {e}"
            prompt_on_failure(ws, idx, initial_fit_col, reason)
            continue

        total = data.get("total")
        if total is None:
            reason = "JSON missing 'total'; agent did not return a score."
            prompt_on_failure(ws, idx, initial_fit_col, reason)
            continue

        try:
            total = int(round(total))
        except (TypeError, ValueError):
            reason = f"'total' is not a number: {total!r}"
            prompt_on_failure(ws, idx, initial_fit_col, reason)
            continue

        total = max(0, min(100, total))

        # Safeguard: same total >= 3 times in a row -> warning and stop
        last_totals.append(total)
        if len(last_totals) > REPEAT_TOTAL_THRESHOLD:
            last_totals.pop(0)
        if len(last_totals) == REPEAT_TOTAL_THRESHOLD and len(set(last_totals)) == 1:
            print(f"\n⚠️ Safeguard: same total {total} repeated {REPEAT_TOTAL_THRESHOLD} times in a row. Stopping (likely broken extraction).", file=sys.stderr)
            sys.exit(1)

        # Sanity: print hashes every row (resume_hash should be same for all; job_hash should differ per job)
        job_hash = data.get("job_hash") or ""
        resume_hash = data.get("resume_hash") or ""
        print(f"  job_hash={job_hash} resume_hash={resume_hash}", file=sys.stderr)
        if first_resume_hash is None:
            first_resume_hash = resume_hash
        elif resume_hash != first_resume_hash:
            print(f"  ⚠️ SANITY: resume_hash changed (was {first_resume_hash!r}, now {resume_hash!r}). Not using same resume for every row?", file=sys.stderr)
        print(f"  → {total} (subscores: {data.get('subscores', {})})")

        log_top5(f"row {idx} {company} {date_iso}", data)

        ws.update_cell(idx, initial_fit_col, total)

    print("\n✅ Done\n")


if __name__ == "__main__":
    main()
