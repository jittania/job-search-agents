import os
from datetime import date, datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv


def parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def main():
    load_dotenv()

    sa_json = os.environ["GOOGLE_SA_JSON"]
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]

    gc = gspread.service_account(filename=sa_json)
    ws = gc.open_by_key(sheet_id).worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip(): i for i, h in enumerate(headers)}

    date_h = "DATE"
    outcome_h = "DATE OF OUTCOME"
    status_h = "STATUS"

    rows = ws.get_all_values()[1:]
    today = date.today()

    applied = 0
    interviews = 0
    offers = 0
    resolved = 0
    times_to_outcome = []

    for r in rows:
        applied_at = parse_date(r[col[date_h]]) if date_h in col else None
        if not applied_at:
            continue

        applied += 1

        status = (r[col[status_h]] if status_h in col else "").lower()
        outcome_date = parse_date(r[col[outcome_h]]) if outcome_h in col else None

        if "interview" in status:
            interviews += 1
        if "offer" in status:
            offers += 1
        if outcome_date:
            resolved += 1
            times_to_outcome.append((outcome_date - applied_at).days)

    median_outcome = (
        sorted(times_to_outcome)[len(times_to_outcome) // 2]
        if times_to_outcome
        else None
    )

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"funnel_stats_{today.isoformat()}.md"

    lines = [
        "# Application Funnel Stats\n\n",
        f"- Generated: {today.isoformat()}\n\n",
        f"- Total applications: {applied}\n",
        f"- Interviews: {interviews}\n",
        f"- Offers: {offers}\n",
        f"- Resolved (any outcome): {resolved}\n",
    ]

    if median_outcome is not None:
        lines.append(f"- Median time to outcome: {median_outcome} days\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"\n✅ Wrote {out_path}")


if __name__ == "__main__":
    main()