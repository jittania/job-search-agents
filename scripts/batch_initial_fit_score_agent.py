"""Batch script: fill 'initial fit score' (0-100) in Google Sheet for rows that don't have it yet."""
import os
import subprocess
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

INITIAL_FIT_SCRIPT = Path(__file__).resolve().parent / "initial_fit_score_agent.py"
DATA_DIR = Path("data")

# Sheet column where we write the 0-100 score (only rows with this empty are processed)
INITIAL_FIT_SCORE_HEADER = "initial fit score"
DATE_APPLIED_HEADER = "date applied"


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

    company_col = col.get("company")
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    initial_fit_col = col.get(INITIAL_FIT_SCORE_HEADER.lower())

    if not company_col:
        raise SystemExit('Sheet must have a column named "COMPANY" (or "company").')
    if not date_applied_col:
        raise SystemExit(f'Sheet must have a column named "{DATE_APPLIED_HEADER}".')
    if not initial_fit_col:
        raise SystemExit(f'Sheet must have a column named "{INITIAL_FIT_SCORE_HEADER}".')

    rows = ws.get_all_values()[1:]

    for idx, row in enumerate(rows, start=2):
        company = (row[company_col - 1] or "").strip()
        date_applied_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        initial_fit_val = (row[initial_fit_col - 1] or "").strip() if initial_fit_col <= len(row) else ""

        if not company or initial_fit_val:
            continue

        date_iso = parse_date_applied(date_applied_raw)
        if not date_iso:
            print(f"Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        job_dir = DATA_DIR / slugify(company) / date_iso
        job_txt = job_dir / "job.txt"
        if not job_txt.exists():
            print(f"Skipping row {idx}: no archived job at {job_dir}")
            continue

        print(f"Scoring row {idx}: {company} | {date_iso}")

        result = subprocess.run(
            ["python", str(INITIAL_FIT_SCRIPT), str(job_dir)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 3 or "SECURITY_CLEARANCE_REQUIRED" in (result.stderr or ""):
            print(f"  ⏭️ Skipped (security clearance required)")
            if initial_fit_col:
                ws.update_cell(idx, initial_fit_col, "N/A (clearance)")
            continue
        if result.returncode != 0:
            print(f"  ⚠️ Failed: {result.stderr or result.stdout}")
            continue

        score = result.stdout.strip()
        if not score.isdigit():
            print(f"  ⚠️ Unexpected output: {score!r}")
            continue

        ws.update_cell(idx, initial_fit_col, score)
        print(f"  → {score}")

    print("\n✅ Done\n")


if __name__ == "__main__":
    main()
