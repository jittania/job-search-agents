"""
Single command: for each new row (no archived_at), archive job, extract metadata,
run initial fit score, and write COMPANY, ROLE TITLE, COMPANY TYPE, COMPANY SIZE BUCKET,
ROLE FOCUS, ROLE LEVEL, and initial fit score to the sheet.

Alias: popjobs
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE_SCRIPT = SCRIPT_DIR / "archive_job_agent.py"
EXTRACT_METADATA_SCRIPT = SCRIPT_DIR / "extract_job_metadata_agent.py"
INITIAL_FIT_SCRIPT = SCRIPT_DIR / "initial_fit_score_agent.py"
CLEARANCE_CHECK_SCRIPT = SCRIPT_DIR / "check_security_clearance.py"
DATA_DIR = Path("data")

DATE_APPLIED_HEADER = "date applied"
INITIAL_FIT_SCORE_HEADER = "initial fit score"

# Sheet column headers (case-insensitive) -> JSON key from extract_job_metadata_agent
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
    company_col = col.get("company name") or col.get("company")
    initial_fit_col = col.get(INITIAL_FIT_SCORE_HEADER.lower())
    job_dir_col = col.get("job_dir") or col.get("archive_path") or col.get("archive path")

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
            print(f"\n⏭️ Skipping row {idx}: no valid '{DATE_APPLIED_HEADER}' (got: {date_applied_raw!r})")
            continue

        # --- 1. Archive (always infer company + role title from job page for consistent folder names) ---
        print(f"\n⬇️  Row {idx}: populating (inferring company + role title) | {url}")
        result = subprocess.run(
            ["python", str(ARCHIVE_SCRIPT), url, date_applied_iso],
            capture_output=True,
            text=True,
            cwd=SCRIPT_DIR.parent,
        )
        if result.returncode == 2 or "POSTING_NOT_FOUND" in (result.stdout or "") + (result.stderr or ""):
            print(f"  ⚠️ Row {idx} skipped: posting not found.")
            continue
        if result.returncode != 0:
            print(f"  ⚠️ Row {idx} archive failed: {result.stderr or result.stdout}")
            continue

        company_display = "Unknown"
        role_title_from_archive = None
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.upper().startswith("COMPANY:"):
                company_display = line.split(":", 1)[1].strip() or "Unknown"
            elif line.upper().startswith("ROLE_TITLE:"):
                role_title_from_archive = line.split(":", 1)[1].strip()

        if company_col and company_display:
            ws.update_cell(idx, company_col, company_display)
        role_title_col = meta_cols.get("role title") if meta_cols else None
        if role_title_col and role_title_from_archive:
            ws.update_cell(idx, role_title_col, role_title_from_archive)

        if (company_display or "").strip() in ("", "Unknown"):
            manual = input(f"  Row {idx}: Could not identify company. Enter company name (or Enter to keep 'Unknown'): ").strip()
            if manual:
                company_display = manual
                if company_col:
                    ws.update_cell(idx, company_col, company_display)

        job_dir = DATA_DIR / slugify(company_display or "unknown") / date_applied_iso
        if job_dir_col:
            ws.update_cell(idx, job_dir_col, str(job_dir))
        if not (job_dir / "job.txt").exists():
            print(f"  ⚠️ No job.txt at {job_dir}; skipping metadata and fit score.")
            ws.update_cell(idx, archived_at_col, datetime.now().isoformat(timespec="seconds"))
            continue

        # --- 1b. Skip if job requires security clearance ---
        result = subprocess.run(
            ["python", str(CLEARANCE_CHECK_SCRIPT), str(job_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 1:
            print(f"  ⏭️ Skipping (security clearance required).")
            if initial_fit_col:
                ws.update_cell(idx, initial_fit_col, "N/A (clearance)")
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
                role_title = (meta.get("role_title") or "").strip()
                if role_title in ("", "Unknown"):
                    manual = input(f"  Row {idx}: Could not identify role title. Enter role title (or Enter to keep 'Unknown'): ").strip()
                    if manual:
                        meta["role_title"] = manual
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
