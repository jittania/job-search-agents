"""
For each job applied on a given date (default: today) from the tracker sheet, copy the resume template
Google Doc into the Drive folder "Company Specific" and rename the copy to:

  <date YYYY-MM-DD>__JittaniaSmith_<company camelCase>_<position camelCase>

Uses OAuth (your Google account) for Drive so copies count against your 2 TB quota,
not the service account's tiny quota.

Requires:
  - GOOGLE_SA_JSON, SHEET_ID, WORKSHEET_NAME (for the tracker sheet)
  - DRIVE_TEMPLATE_DOC_ID, DRIVE_COMPANY_SPECIFIC_FOLDER_ID (in .env)
  - OAuth: credentials.json (Desktop app client secrets from GCP) in project root,
    or DRIVE_CREDENTIALS_JSON path. First run opens browser to sign in; token saved to .drive_oauth_token.json
"""
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

DATE_APPLIED_HEADER = "date applied"
# Default template Doc ID from the shared URL (override with env DRIVE_TEMPLATE_DOC_ID)
DEFAULT_TEMPLATE_DOC_ID = "1dlf2MutB41W-yOKWgjVdAJ_838QC0y-wChZSiASiIsc"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def to_camel_case(s: str) -> str:
    """PascalCase: 'Acme Corp' -> 'AcmeCorp', 'Senior Software Engineer' -> 'SeniorSoftwareEngineer'."""
    s = (s or "").strip()
    if not s:
        return "Unknown"
    # Split on non-alphanumeric, capitalize each word, join
    words = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().split()
    return "".join(w.capitalize() for w in words) if words else "Unknown"


def get_drive_credentials() -> OAuthCredentials:
    """Load OAuth credentials for Drive (user's account so copies use their quota)."""
    load_dotenv()
    project_root = Path(__file__).resolve().parent.parent
    creds_path = os.environ.get("DRIVE_CREDENTIALS_JSON", str(project_root / "credentials.json"))
    token_path = os.environ.get("DRIVE_TOKEN_JSON", str(project_root / ".drive_oauth_token.json"))

    creds = None
    if os.path.exists(token_path):
        creds = OAuthCredentials.from_authorized_user_file(token_path, DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise SystemExit(
                    f"OAuth credentials not found at {creds_path}. "
                    "Create an OAuth 2.0 Desktop client in GCP Console (APIs & Services > Credentials > Create Client > Desktop app), "
                    "download the JSON, and save it as credentials.json in the project root (or set DRIVE_CREDENTIALS_JSON)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


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

    # Optional: python duplicate_resume_docs.py [YYYY-MM-DD] — default is today
    target_date_iso = date.today().isoformat()
    if len(sys.argv) >= 2:
        arg = sys.argv[1].strip()
        if len(arg) == 10 and arg[4] == "-" and arg[7] == "-":
            try:
                datetime.strptime(arg, "%Y-%m-%d")
                target_date_iso = arg
            except ValueError:
                pass

    sa_json = os.environ.get("GOOGLE_SA_JSON", "").strip()
    sheet_id = os.environ["SHEET_ID"]
    worksheet_name = os.environ["WORKSHEET_NAME"]
    template_id = os.environ.get("DRIVE_TEMPLATE_DOC_ID", DEFAULT_TEMPLATE_DOC_ID).strip()
    folder_id = os.environ.get("DRIVE_COMPANY_SPECIFIC_FOLDER_ID", "").strip()

    if not sa_json:
        raise SystemExit("Set GOOGLE_SA_JSON in .env to the path of your service account JSON file (e.g. google_service_account.json).")
    sa_path = Path(sa_json)
    if not sa_path.is_file():
        hint = ""
        if folder_id and len(folder_id) > 20 and "/" not in folder_id and "\\" not in folder_id:
            hint = " (If you put the Drive folder ID here by mistake, use GOOGLE_SA_JSON for the JSON key file path and DRIVE_COMPANY_SPECIFIC_FOLDER_ID for the folder ID.)"
        raise SystemExit(f"GOOGLE_SA_JSON is not an existing file: {sa_json!r}{hint}")

    if not folder_id:
        raise SystemExit(
            "Set DRIVE_COMPANY_SPECIFIC_FOLDER_ID to the Google Drive folder ID for "
            "'Company Specific' (Career > 2024-2026 > Resumes > Company Specific). "
            "Get it from the folder URL when opened in Drive."
        )

    gc = gspread.service_account(filename=sa_json)
    sh = gc.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet_name)

    headers = ws.row_values(1)
    col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}

    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    company_col = col.get("company")
    role_title_col = col.get("role title")

    if not date_applied_col or not company_col or not role_title_col:
        raise SystemExit(
            "Sheet must have columns: date applied, company, role title."
        )

    rows = ws.get_all_values()[1:]
    today_rows = []
    for row in rows:
        date_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        date_iso = parse_date_applied(date_raw)
        if date_iso != target_date_iso:
            continue
        company = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
        role_title = (row[role_title_col - 1] or "").strip() if role_title_col <= len(row) else ""
        if not company:
            continue
        today_rows.append((date_iso, company, role_title or "Role"))

    if not today_rows:
        print(f"No applications found for date {target_date_iso}.")
        return

    drive_creds = get_drive_credentials()
    drive = build("drive", "v3", credentials=drive_creds)

    for date_iso, company, position in today_rows:
        company_camel = to_camel_case(company)
        position_camel = to_camel_case(position)
        name = f"{date_iso}__JittaniaSmith_{company_camel}_{position_camel}"

        body = {"name": name, "parents": [folder_id]}
        try:
            new_file = drive.files().copy(
                fileId=template_id,
                body=body,
                supportsAllDrives=True,
            ).execute()
            new_id = new_file.get("id")
            print(f"✅ {name}  (id={new_id})")
        except Exception as e:
            err_str = str(e)
            if "404" in err_str and folder_id in err_str:
                print(
                    f"❌ {name}: Destination folder not found. Check DRIVE_COMPANY_SPECIFIC_FOLDER_ID (open the Company Specific folder in Drive; the URL has .../folders/<ID>)."
                )
            elif "404" in err_str and template_id in err_str:
                print(
                    f"❌ {name}: Template doc not found. Ensure the template Doc is in your Drive (or shared with you) and DRIVE_TEMPLATE_DOC_ID is correct."
                )
            elif "storageQuotaExceeded" in err_str or "storage quota" in err_str.lower():
                print(
                    f"❌ {name}: Drive storage quota exceeded. This script uses OAuth (your account)—check your Drive quota, or ensure you're not using a service account for Drive (see README)."
                )
            else:
                print(f"❌ {name}: {e}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
