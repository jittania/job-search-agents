"""
For each tracker row that has a posting link and no archived_at, archive the job
(Playwright + job.txt, raw.html, job.pdf under data/<company>/<date>/) and set archived_at.
Company and role title are inferred from the job page and written to the sheet; archive_path
is written when the column exists so batch_extract_metadata can find the folder later.
Does not run metadata or fit score.

Alias: archivejobs
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

ARCHIVE_SCRIPT = Path(__file__).resolve().parent / "archive_job_agent.py"
DATA_DIR = Path("data")

# Header name for the "date applied" column (used for folder name under data/company/)
DATE_APPLIED_HEADER = "date applied"
JOB_DIR_HEADERS = ("job_dir", "archive_path", "archive path")


def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def parse_date_applied(raw: str) -> str | None:
    """Parse date applied from sheet into YYYY-MM-DD, or return None if missing/invalid."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # Already ISO (YYYY-MM-DD)
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            pass
    # MM/DD/YYYY or M/D/YYYY (US-style)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # M/D/YY or M/D/YYYY (e.g. 1/30/26, 2/4/26, 2/10/2025)
    parts = raw.split("/")
    if len(parts) == 3:
        try:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:  # 2-digit year: 26 -> 2026
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
    col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}  # 1-based, case-insensitive

    archived_at_col = col["archived_at"]
    company_col = col.get("company name") or col.get("company")
    role_title_col = col.get("role title")
    url_col = col["posting link"]
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    job_dir_col = next((col.get(h) for h in JOB_DIR_HEADERS if col.get(h)), None)
    if not date_applied_col:
        raise SystemExit(f'Sheet must have a column named "{DATE_APPLIED_HEADER}" (used for folder date).')
    if not company_col:
        raise SystemExit('Sheet must have a column named "COMPANY NAME" or "company" (written after archive).')

    rows = ws.get_all_values()[1:]  # skip header

    for idx, row in enumerate(rows, start=2):  # sheet row numbers
        archived_at = (row[archived_at_col - 1] or "").strip()
        url = (row[url_col - 1] or "").strip()
        date_applied_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""

        if not url or archived_at:
            continue

        date_applied_iso = parse_date_applied(date_applied_raw)
        if not date_applied_iso:
            print(f"\n⏭️ Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        print(f"\n⬇️ Populating row {idx}: (inferring company + role title) | {url} | {date_applied_iso}")
        result = subprocess.run(
            ["python", str(ARCHIVE_SCRIPT), url, date_applied_iso],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            check=False,
        )
        if result.returncode != 0:
            print(f"  ⚠️ Archive failed: {result.stderr or result.stdout}")
            continue

        inferred_company = None
        inferred_role_title = None
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.upper().startswith("COMPANY:"):
                inferred_company = line.split(":", 1)[1].strip()
            elif line.upper().startswith("ROLE_TITLE:"):
                inferred_role_title = line.split(":", 1)[1].strip()

        if company_col and inferred_company:
            ws.update_cell(idx, company_col, inferred_company)
        if role_title_col and inferred_role_title:
            ws.update_cell(idx, role_title_col, inferred_role_title)

        if job_dir_col and inferred_company:
            archive_path = str(DATA_DIR / slugify(inferred_company) / date_applied_iso)
            ws.update_cell(idx, job_dir_col, archive_path)

        ws.update_cell(idx, archived_at_col, datetime.now().isoformat(timespec="seconds"))

    print("\nDone\n")

if __name__ == "__main__":
    main()