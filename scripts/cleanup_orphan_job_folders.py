"""
Delete data/<company>/<date>/ folders that no longer have a row in the tracker sheet
(e.g. you deleted the row or didn't apply). Use --dry-run to list would-be-removed folders only.

Alias: cleanup
"""
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

DATA_DIR = Path("data")
DATE_APPLIED_HEADER = "date applied"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in (s or "").strip()).strip("-")


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
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    if dry_run:
        print("(dry run — no folders will be deleted)\n")

    load_dotenv()
    sa_json = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not sa_json or not Path(sa_json).is_file():
        raise SystemExit("Set GOOGLE_SA_JSON in .env to the path of your Google service account JSON.")
    gc = gspread.service_account(filename=sa_json)
    sh = gc.open_by_key(os.environ["SHEET_ID"]).worksheet(os.environ["WORKSHEET_NAME"])
    headers = sh.row_values(1)
    col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    company_col = col.get("company")
    if not date_applied_col or not company_col:
        raise SystemExit("Sheet must have columns: date applied, company.")

    rows = sh.get_all_values()[1:]
    keep = set()
    for row in rows:
        date_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        date_iso = parse_date_applied(date_raw)
        if not date_iso:
            continue
        company = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
        if not company:
            continue
        keep.add((slugify(company), date_iso))

    if not DATA_DIR.exists():
        print("No data/ directory.")
        return

    removed = 0
    for company_dir in sorted(DATA_DIR.iterdir()):
        if not company_dir.is_dir():
            continue
        for date_dir in sorted(company_dir.iterdir()):
            if not date_dir.is_dir() or not DATE_PATTERN.match(date_dir.name):
                continue
            key = (company_dir.name, date_dir.name)
            if key in keep:
                continue
            path = company_dir / date_dir.name
            print(f"  {'Would remove' if dry_run else 'Removing'}: {path.relative_to(DATA_DIR)}")
            if not dry_run:
                shutil.rmtree(path)
            removed += 1

    # Remove company directories that are now empty (no date subdirs left).
    for company_dir in sorted(DATA_DIR.iterdir()):
        if not company_dir.is_dir():
            continue
        try:
            subs = list(company_dir.iterdir())
        except OSError:
            continue
        # Only remove if empty or only non-date items (e.g. no YYYY-MM-DD subdirs).
        date_subdirs = [s for s in subs if s.is_dir() and DATE_PATTERN.match(s.name)]
        if date_subdirs:
            continue
        print(f"  {'Would remove' if dry_run else 'Removing'} (empty company dir): {company_dir.relative_to(DATA_DIR)}")
        if not dry_run:
            shutil.rmtree(company_dir)
        removed += 1

    if removed == 0:
        print("No orphan folders found.")
    else:
        print(f"\n✅ {'Would remove' if dry_run else 'Removed'} {removed} folder(s).")


if __name__ == "__main__":
    main()
