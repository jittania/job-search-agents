"""
Generate skills_recommendations.json for job folders for a given day (default today) from the
tracker sheet. Overwrites existing file in each folder.

Alias: evalskills [today|YYYY-MM-DD]
"""
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
EVAL_SKILLS_SCRIPT = SCRIPT_DIR / "evaluate_resume_skills_agent.py"
DATA_DIR = Path("data")
OUTPUT_FILE = "skills_recommendations.json"
DATE_APPLIED_HEADER = "date applied"


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


def is_job_dir_path(arg: str) -> bool:
    p = Path(arg).resolve()
    return p.is_dir() and (p / "job.txt").exists()


def main():
    if len(sys.argv) == 2 and is_job_dir_path(sys.argv[1]):
        job_dir = Path(sys.argv[1]).resolve()
        print(f"📋 Skills (single): {job_dir}")
        subprocess.run(["python", str(EVAL_SKILLS_SCRIPT), str(job_dir)], check=True)
        return

    day = date.today().isoformat()
    if len(sys.argv) == 2:
        arg = sys.argv[1].strip().lower()
        if arg == "today":
            day = date.today().isoformat()
        else:
            day = arg

    if not DATA_DIR.exists():
        raise SystemExit("Missing data/ directory.")

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
    target_dirs = []
    for row in rows:
        date_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        date_iso = parse_date_applied(date_raw)
        if date_iso != day:
            continue
        company = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
        if not company:
            continue
        job_dir = DATA_DIR / slugify(company) / date_iso
        if not (job_dir / "job.txt").exists():
            continue
        target_dirs.append(job_dir)

    wrote = 0
    for job_dir in target_dirs:
        print(f"📋 Skills: {job_dir.relative_to(DATA_DIR)}")
        subprocess.run(
            ["python", str(EVAL_SKILLS_SCRIPT), str(job_dir)],
            check=True,
        )
        wrote += 1

    print(f"\n✅ Done. wrote={wrote}\n")


if __name__ == "__main__":
    main()
