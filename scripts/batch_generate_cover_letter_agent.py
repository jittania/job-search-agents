"""Batch: generate cover letters and upload them to the cover letters Google Drive folder as .docx (same naming as dupcl). Skips job dirs that don't have job.txt."""
import io
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import gspread
from anthropic import Anthropic
from docx import Document
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("data")
DATE_APPLIED_HEADER = "date applied"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def to_camel_case(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "Unknown"
    words = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().split()
    return "".join(w.capitalize() for w in words) if words else "Unknown"


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
                raise SystemExit(f"OAuth credentials not found at {creds_path}. Use same credentials.json as dupres/dupcl.")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def make_docx_from_text(text: str) -> bytes:
    doc = Document()
    for para in text.strip().split("\n\n"):
        doc.add_paragraph(para.strip())
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def generate_letter(job_dir: Path, client: Anthropic) -> str:
    job_txt = job_dir / "job.txt"
    url_txt = job_dir / "url.txt"
    resume_path = Path("data/resume.txt")
    job_text = job_txt.read_text(encoding="utf-8")
    resume_text = resume_path.read_text(encoding="utf-8")
    url = url_txt.read_text(encoding="utf-8").strip() if url_txt.exists() else ""
    prompt = f"""Write a concise, confident cover letter tailored to this job.

Constraints:
- 220–320 words
- 3 short paragraphs max
- No buzzword soup
- No claims you can't support from the resume
- Reference the company/role naturally (if the JD provides it)
- End with a simple call to action
- Output plain text ONLY

JOB POSTING URL (if available):
{url}

JOB DESCRIPTION:
{job_text}

RESUME:
{resume_text}
"""
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt.strip()}],
    )
    letter = (msg.content[0].text or "").strip()
    if not letter:
        raise RuntimeError("Claude returned empty cover letter")
    return letter


def is_job_dir_path(arg: str) -> bool:
    p = Path(arg).resolve()
    return p.is_dir() and (p / "job.txt").exists()


def main():
    load_dotenv()

    # Single job path: gencl data/costco/2026-02-10 → generate and upload to Drive (need company/role from sheet)
    if len(sys.argv) == 2 and is_job_dir_path(sys.argv[1]):
        job_dir = Path(sys.argv[1]).resolve()
        company_slug = job_dir.parent.name
        date_iso = job_dir.name
        sa_json = os.environ.get("GOOGLE_SA_JSON", "").strip()
        folder_id = os.environ.get("DRIVE_COVER_LETTERS_FOLDER_ID", "").strip()
        if not folder_id or not sa_json or not Path(sa_json).is_file():
            raise SystemExit("Set GOOGLE_SA_JSON and DRIVE_COVER_LETTERS_FOLDER_ID in .env.")
        gc = gspread.service_account(filename=sa_json)
        sh = gc.open_by_key(os.environ["SHEET_ID"]).worksheet(os.environ["WORKSHEET_NAME"])
        headers = sh.row_values(1)
        col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}
        date_col = col.get(DATE_APPLIED_HEADER.lower())
        company_col = col.get("company")
        role_col = col.get("role title")
        if not all([date_col, company_col, role_col]):
            raise SystemExit("Sheet must have date applied, company, role title.")
        rows = sh.get_all_values()[1:]
        company_display = role_title = None
        for row in rows:
            if date_col <= len(row) and parse_date_applied((row[date_col - 1] or "").strip()) != date_iso:
                continue
            c = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
            if slugify(c) == company_slug:
                company_display = c
                role_title = (row[role_col - 1] or "").strip() if role_col <= len(row) else "Role"
                break
        if not company_display:
            raise SystemExit(f"Could not find sheet row for {job_dir}. Ensure date applied and company match.")
        name = f"{date_iso}__JittaniaSmith_{to_camel_case(company_display)}_{to_camel_case(role_title)}.docx"
        letter = generate_letter(job_dir, Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))
        docx_bytes = make_docx_from_text(letter)
        drive = build("drive", "v3", credentials=get_drive_credentials())
        media = MediaIoBaseUpload(io.BytesIO(docx_bytes), mimetype=DOCX_MIME, resumable=False)
        resp = drive.files().list(q=f"'{folder_id}' in parents and name='{name}'", fields="files(id, name)").execute()
        files = resp.get("files", [])
        if files:
            drive.files().update(fileId=files[0]["id"], media_body=media).execute()
            print(f"✅ Updated {name}\n")
        else:
            body = {"name": name, "parents": [folder_id]}
            drive.files().create(body=body, media_body=media, fields="id").execute()
            print(f"✅ Created {name}\n")
        return

    # Batch path: by date (today or YYYY-MM-DD)
    target_date_iso = date.today().isoformat()
    if len(sys.argv) == 2:
        arg = sys.argv[1].strip().lower()
        if arg != "today" and len(arg) == 10 and arg[4] == "-" and arg[7] == "-":
            try:
                datetime.strptime(arg, "%Y-%m-%d")
                target_date_iso = arg
            except ValueError:
                pass

    sa_json = os.environ.get("GOOGLE_SA_JSON", "").strip()
    folder_id = os.environ.get("DRIVE_COVER_LETTERS_FOLDER_ID", "").strip()
    if not sa_json or not Path(sa_json).is_file():
        raise SystemExit("Set GOOGLE_SA_JSON in .env.")
    if not folder_id:
        raise SystemExit("Set DRIVE_COVER_LETTERS_FOLDER_ID in .env (same as dupcl).")

    gc = gspread.service_account(filename=sa_json)
    sh = gc.open_by_key(os.environ["SHEET_ID"]).worksheet(os.environ["WORKSHEET_NAME"])
    headers = sh.row_values(1)
    col = {h.strip().lower(): i + 1 for i, h in enumerate(headers)}
    date_applied_col = col.get(DATE_APPLIED_HEADER.lower())
    company_col = col.get("company")
    role_title_col = col.get("role title")
    if not date_applied_col or not company_col or not role_title_col:
        raise SystemExit("Sheet must have columns: date applied, company, role title.")

    rows = sh.get_all_values()[1:]
    target_rows = []
    for row in rows:
        date_raw = (row[date_applied_col - 1] or "").strip() if date_applied_col <= len(row) else ""
        date_iso = parse_date_applied(date_raw)
        if date_iso != target_date_iso:
            continue
        company = (row[company_col - 1] or "").strip() if company_col <= len(row) else ""
        role_title = (row[role_title_col - 1] or "").strip() if role_title_col <= len(row) else "Role"
        if not company:
            continue
        job_dir = DATA_DIR / slugify(company) / date_iso
        if not (job_dir / "job.txt").exists():
            continue
        target_rows.append((date_iso, company, role_title, job_dir))

    if not target_rows:
        print(f"No jobs with archived job.txt found for date {target_date_iso}.")
        return

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    drive = build("drive", "v3", credentials=get_drive_credentials())
    # List existing files in folder to support update-by-name
    existing = {}
    page = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType='{DOCX_MIME}'",
            fields="nextPageToken, files(id, name)",
            pageToken=page or "",
        ).execute()
        for f in resp.get("files", []):
            existing[f["name"]] = f["id"]
        page = resp.get("nextPageToken")
        if not page:
            break

    wrote = 0
    for date_iso, company, role_title, job_dir in target_rows:
        name = f"{date_iso}__JittaniaSmith_{to_camel_case(company)}_{to_camel_case(role_title)}.docx"
        print(f"📄 Cover letter: {job_dir.relative_to(DATA_DIR)}")
        try:
            letter = generate_letter(job_dir, client)
        except Exception as e:
            print(f"  ⚠️ Generate failed: {e}")
            continue
        docx_bytes = make_docx_from_text(letter)
        media = MediaIoBaseUpload(io.BytesIO(docx_bytes), mimetype=DOCX_MIME, resumable=False)
        try:
            if name in existing:
                drive.files().update(fileId=existing[name], media_body=media).execute()
                print(f"  ✅ Updated {name}")
            else:
                body = {"name": name, "parents": [folder_id]}
                drive.files().create(body=body, media_body=media, fields="id").execute()
                print(f"  ✅ Created {name}")
            wrote += 1
        except Exception as e:
            print(f"  ⚠️ Drive upload failed: {e}")

    print(f"\n✅ Done. wrote={wrote}\n")


if __name__ == "__main__":
    main()
