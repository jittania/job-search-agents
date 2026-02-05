import os
import subprocess
from datetime import datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv

ARCHIVE_SCRIPT = Path("scripts/archive_job.py")

def main():
    load_dotenv()

    sa_json = os.environ["GOOGLE_SA_JSON"]
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]

    gc = gspread.service_account(filename=sa_json)
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip(): i + 1 for i, h in enumerate(headers)}  # 1-based

    archived_at_col = col["archived_at"]
    company_col = col["COMPANY"]
    url_col = col["POSTING LINK"]

    rows = ws.get_all_values()[1:]  # skip header

    for idx, row in enumerate(rows, start=2):  # sheet row numbers
        archived_at = (row[archived_at_col - 1] or "").strip()
        company = (row[company_col - 1] or "").strip()
        url = (row[url_col - 1] or "").strip()

        if not url or not company or archived_at:
            continue

        print(f"Archiving row {idx}: {company} | {url}")

        subprocess.run(
            ["python", str(ARCHIVE_SCRIPT), company, url],
            check=True,
        )

        ws.update_cell(idx, archived_at_col, datetime.now().isoformat(timespec="seconds"))

    print("\n✅ Done\n")

if __name__ == "__main__":
    main()