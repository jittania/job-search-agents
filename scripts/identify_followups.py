import os
import sys
from datetime import date, datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv


def parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None

    # Normalize common Sheets quirks
    s = s.replace("\u200e", "").replace("\u200f", "")  # invisible LTR/RTL marks

    # Try ISO / timestamp-ish
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except ValueError:
        pass

    # Try common date formats from Sheets
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Last resort: if it starts with YYYY-MM-DD
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    load_dotenv()

    # Default threshold (days since applied)
    days = 10
    if len(sys.argv) == 2:
        days = int(sys.argv[1])

    sa_json = os.environ["GOOGLE_SA_JSON"]
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]

    gc = gspread.service_account(filename=sa_json)
    ws = gc.open_by_key(sheet_id).worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip(): i for i, h in enumerate(headers)}  # 0-based

    # Sheet headers (must match your sheet exactly)
    date_h = "DATE"
    company_h = "COMPANY"
    role_h = "ROLE TITLE"
    link_h = "POSTING LINK"
    outcome_date_h = "DATE OF OUTCOME"

    rows = ws.get_all_values()[1:]  # skip header
    today = date.today()

    followups = []

    for r in rows:
        posting_link = (r[col[link_h]] if link_h in col else "").strip()
        if not posting_link:
            continue

        applied_at = parse_date(r[col[date_h]]) if date_h in col else None
        if not applied_at:
            continue

        # If DATE OF OUTCOME is filled, job is resolved → no follow-up
        outcome_date = (r[col[outcome_date_h]] if outcome_date_h in col else "").strip()
        if outcome_date:
            continue

        age_days = (today - applied_at).days
        if age_days < days:
            continue

        company = (r[col[company_h]] if company_h in col else "").strip()
        role = (r[col[role_h]] if role_h in col else "").strip()

        followups.append(
            {
                "company": company,
                "role": role,
                "applied_at": applied_at.isoformat(),
                "age_days": age_days,
                "link": posting_link,
            }
        )

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"followups_{today.isoformat()}.md"

    lines = []
    lines.append(f"# Follow-ups to send (>= {days} days)\n\n")
    lines.append(f"- Generated: {today.isoformat()}\n")
    lines.append(f"- Count: {len(followups)}\n\n")

    for item in sorted(followups, key=lambda x: x["age_days"], reverse=True):
        lines.append(
            f"- {item['company']} — {item['role']} (applied {item['applied_at']}, {item['age_days']}d) — {item['link']}\n"
        )

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"\n✅ Wrote {out_path} ({len(followups)} jobs)")


if __name__ == "__main__":
    main()