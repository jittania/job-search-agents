"""
For each job applied on a given date (default: today) from the tracker sheet, create a blank
Word document and upload it to a Google Drive folder, named:

  <date YYYY-MM-DD>__JittaniaSmith_<company camelCase>_<position camelCase>.docx

Uses the same OAuth and sheet setup as duplicate_resume_docs. Requires DRIVE_COVER_LETTERS_FOLDER_ID in .env.
"""
import io
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import gspread
from docx import Document
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

DATE_APPLIED_HEADER = "date applied"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def to_camel_case(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "Unknown"
    words = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().split()
    return "".join(w.capitalize() for w in words) if words else "Unknown"


def get_drive_credentials() -> OAuthCredentials:
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
                    "Use the same credentials.json as duplicate_resume_docs (see README)."
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


def make_blank_docx() -> bytes:
    doc = Document()
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def main():
    load_dotenv()

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
    folder_id = os.environ.get("DRIVE_COVER_LETTERS_FOLDER_ID", "").strip()

    if not sa_json or not Path(sa_json).is_file():
        raise SystemExit("Set GOOGLE_SA_JSON in .env to the path of your service account JSON file.")
    if not folder_id:
        raise SystemExit(
            "Set DRIVE_COVER_LETTERS_FOLDER_ID in .env to the Google Drive folder ID for cover letters "
            "(e.g. Career > 2024-2026 > Cover Letters). Get it from the folder URL: .../folders/<ID>"
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
        raise SystemExit("Sheet must have columns: date applied, company, role title.")

    rows = ws.get_all_values()[1:]
    target_rows = []
    for row in rows:
        date_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        date_iso = parse_date_applied(date_raw)
        if date_iso != target_date_iso:
            continue
        company = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
        role_title = (row[role_title_col - 1] or "").strip() if role_title_col <= len(row) else ""
        if not company:
            continue
        target_rows.append((date_iso, company, role_title or "Role"))

    if not target_rows:
        print(f"No applications found for date {target_date_iso}.")
        return

    docx_bytes = make_blank_docx()
    drive_creds = get_drive_credentials()
    drive = build("drive", "v3", credentials=drive_creds)

    for date_iso, company, position in target_rows:
        company_camel = to_camel_case(company)
        position_camel = to_camel_case(position)
        name = f"{date_iso}__JittaniaSmith_{company_camel}_{position_camel}.docx"

        body = {"name": name, "parents": [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(docx_bytes), mimetype=DOCX_MIME, resumable=False)
        try:
            new_file = drive.files().create(
                body=body,
                media_body=media,
                fields="id",
            ).execute()
            print(f"✅ {name}  (id={new_file.get('id')})")
        except Exception as e:
            err_str = str(e)
            if "404" in err_str and folder_id in err_str:
                print(f"❌ {name}: Folder not found. Check DRIVE_COVER_LETTERS_FOLDER_ID.")
            else:
                print(f"❌ {name}: {e}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
