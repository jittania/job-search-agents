"""
Single command: for each new row (no archived_at), archive job, extract metadata,
run initial fit score, and write COMPANY, ROLE TITLE, COMPANY TYPE, COMPANY SIZE BUCKET,
ROLE FOCUS, ROLE LEVEL, and initial fit score to the sheet.
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_SCRIPT = SCRIPT_DIR / "archive_job.py"
EXTRACT_METADATA_SCRIPT = SCRIPT_DIR / "extract_job_metadata.py"
INITIAL_FIT_SCRIPT = SCRIPT_DIR / "initial_fit_score_agent.py"
DATA_DIR = Path("data")

DATE_APPLIED_HEADER = "date applied"
INITIAL_FIT_SCORE_HEADER = "initial fit score"

# Sheet column headers (case-insensitive) -> JSON key from extract_job_metadata
METADATA_COLUMNS = {
    "role title": "role_title",
    "company type": "company_type",
    "company size bucket": "company_size_bucket",
    "role focus": "role_focus",
    "role level": "role_level",
}


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

    archived_at_col = col["archived_at"]
    url_col = col["posting link"]
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    company_col = col.get("company")
    initial_fit_col = col.get(INITIAL_FIT_SCORE_HEADER.lower())

    if not date_applied_col:
        raise SystemExit(f'Sheet must have column "{DATE_APPLIED_HEADER}".')
    meta_cols = {header: col.get(header) for header in METADATA_COLUMNS}
    missing = [k for k, v in meta_cols.items() if not v]
    if missing:
        raise SystemExit(f'Sheet missing columns: {missing}')

    rows = ws.get_all_values()[1:]

    for idx, row in enumerate(rows, start=2):
        archived_at = (row[archived_at_col - 1] or "").strip()
        url = (row[url_col - 1] or "").strip()
        date_applied_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        company_from_sheet = (row[company_col - 1] or "").strip() if company_col and company_col <= len(row) else ""

        if not url or archived_at:
            continue

        date_applied_iso = parse_date_applied(date_applied_raw)
        if not date_applied_iso:
            print(f"⚠️ Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        # --- 1. Archive ---
        if company_from_sheet:
            print(f"\n⬇️ Row {idx}: archiving {company_from_sheet} | {url}")
            subprocess.run(
                ["python", str(ARCHIVE_SCRIPT), company_from_sheet, url, date_applied_iso],
                check=True,
            )
            company_display = company_from_sheet
        else:
            print(f"\n⬇️ Row {idx}: archiving (inferring company) | {url}")
            result = subprocess.run(
                ["python", str(ARCHIVE_SCRIPT), url, date_applied_iso],
                capture_output=True,
                text=True,
                check=True,
            )
            company_display = "Unknown"
            for line in (result.stdout or "").splitlines():
                if line.startswith("COMPANY: "):
                    company_display = line.removeprefix("COMPANY: ").strip()
                    if company_col:
                        ws.update_cell(idx, company_col, company_display)
                    break

        job_dir = DATA_DIR / slugify(company_display) / date_applied_iso
        if not (job_dir / "job.txt").exists():
            print(f"  ⚠️ No job.txt at {job_dir}; skipping metadata and fit score.")
            ws.update_cell(idx, archived_at_col, datetime.now().isoformat(timespec="seconds"))
            continue

        # --- 2. Extract metadata ---
        print(f"  📋 Extracting metadata…")
        result = subprocess.run(
            ["python", str(EXTRACT_METADATA_SCRIPT), str(job_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"  ⚠️ Metadata extraction failed: {result.stderr or result.stdout}")
        else:
            try:
                meta = json.loads(result.stdout.strip())
                # Coerce role_level to sheet dropdown: MID | SENIOR (map others)
                if "role_level" in meta:
                    rl = meta["role_level"].upper()
                    if rl in ("JUNIOR",):
                        meta["role_level"] = "MID"
                    elif rl in ("STAFF", "PRINCIPAL"):
                        meta["role_level"] = "SENIOR"
                for header, json_key in METADATA_COLUMNS.items():
                    c = meta_cols.get(header)
                    if c and json_key in meta:
                        ws.update_cell(idx, c, meta[json_key])
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ⚠️ Could not parse metadata: {e}")

        # --- 3. Initial fit score ---
        if initial_fit_col:
            print(f"  📊 Initial fit score…")
            result = subprocess.run(
                ["python", str(INITIAL_FIT_SCRIPT), str(job_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                ws.update_cell(idx, initial_fit_col, result.stdout.strip())
                print(f"  → score: {result.stdout.strip()}")
            else:
                print(f"  ⚠️ Fit score failed: {result.stderr or result.stdout}")

        ws.update_cell(idx, archived_at_col, datetime.now().isoformat(timespec="seconds"))
        print(f"  ✅ Row {idx} done.")

    print("\n✅ populatejobs done.\n")


if __name__ == "__main__":
    main()
