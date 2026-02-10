import csv
import os
from pathlib import Path

import gspread
from dotenv import load_dotenv


OUT_PATH = Path("data/job_index.csv")


def slugify(s: str) -> str:
    s = (s or "").strip()
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def date_part(archived_at: str) -> str:
    # handles "2026-02-04 23:19:17" or "2026-02-04T23:19:17"
    s = (archived_at or "").strip()
    return s[:10] if len(s) >= 10 else ""


def main():
    load_dotenv()

    sa_json = os.environ["GOOGLE_SA_JSON"]
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]

    gc = gspread.service_account(filename=sa_json)
    ws = gc.open_by_key(sheet_id).worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip(): i for i, h in enumerate(headers)}  # 0-based

    # Your sheet headers (as shown in your screenshots)
    company_h = "COMPANY"
    role_h = "ROLE TITLE"
    url_h = "POSTING LINK"
    archived_h = "archived_at"

    rows = ws.get_all_values()[1:]  # skip header

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "job_id",
                "company",
                "role_title",
                "posting_link",
                "archived_at",
                "archive_path",
            ],
        )
        writer.writeheader()

        count = 0
        for r in rows:
            company = (r[col[company_h]] if company_h in col else "").strip()
            role_title = (r[col[role_h]] if role_h in col else "").strip()
            posting_link = (r[col[url_h]] if url_h in col else "").strip()
            archived_at = (r[col[archived_h]] if archived_h in col else "").strip()

            if not posting_link:
                continue

            # Stable ID: URL is good enough for now
            job_id = posting_link

            # Only fill archive_path if it’s archived
            ap = ""
            dp = date_part(archived_at)
            if dp and company:
                ap = str(Path("data") / slugify(company) / dp)

            writer.writerow(
                {
                    "job_id": job_id,
                    "company": company,
                    "role_title": role_title,
                    "posting_link": posting_link,
                    "archived_at": archived_at,
                    "archive_path": ap,
                }
            )
            count += 1

    print(f"\n✅ Wrote {OUT_PATH} ({count} rows)\n")


if __name__ == "__main__":
    main()