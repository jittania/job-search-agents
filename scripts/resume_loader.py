"""
Single source for resume text: Google Doc only.
Set RESUME_GOOGLE_DOC_ID or RESUME_GOOGLE_DOC_URL in .env. Uses same OAuth as dupres.
Raises if not configured or if the Doc cannot be fetched.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _doc_id_from_url(url: str) -> str | None:
    """Extract Google Doc ID from docs.google.com/document/d/DOC_ID/..."""
    if not url or "docs.google.com/document/d/" not in url:
        return None
    m = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url.strip())
    return m.group(1) if m else None


def _get_drive_credentials():
    """OAuth credentials for Drive (same pattern as duplicate_resume_docs)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    load_dotenv()
    creds_path = os.environ.get("DRIVE_CREDENTIALS_JSON", str(PROJECT_ROOT / "credentials.json"))
    token_path = os.environ.get("DRIVE_TOKEN_JSON", str(PROJECT_ROOT / ".drive_oauth_token.json"))

    creds = None
    if os.path.exists(token_path):
        creds = OAuthCredentials.from_authorized_user_file(token_path, DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def _fetch_resume_from_google_doc(doc_id: str) -> tuple[str | None, str | None]:
    """Export Google Doc as plain text via Drive API. Returns (text, error_message)."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        creds = _get_drive_credentials()
        if not creds:
            return None, "Drive OAuth not available. Add credentials.json (or set DRIVE_CREDENTIALS_JSON) and re-run to authorize."
        drive = build("drive", "v3", credentials=creds)
        request = drive.files().export_media(fileId=doc_id, mimeType="text/plain")
        import io

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        text = fh.getvalue().decode("utf-8", errors="replace")
        return (text, None) if text and text.strip() else (None, "Google Doc is empty or export returned no text.")
    except Exception as e:
        return None, str(e)


def get_resume_text() -> str:
    """
    Return resume text from Google Doc. Requires RESUME_GOOGLE_DOC_ID or RESUME_GOOGLE_DOC_URL in .env.
    Raises FileNotFoundError if not configured; raises RuntimeError if the Doc cannot be fetched.
    """
    load_dotenv()
    doc_id = os.environ.get("RESUME_GOOGLE_DOC_ID", "").strip()
    if not doc_id:
        url = os.environ.get("RESUME_GOOGLE_DOC_URL", "").strip()
        doc_id = _doc_id_from_url(url) if url else None
    if not doc_id:
        raise FileNotFoundError(
            "Resume: set RESUME_GOOGLE_DOC_ID or RESUME_GOOGLE_DOC_URL in .env to your resume Google Doc."
        )
    text, err = _fetch_resume_from_google_doc(doc_id)
    if err:
        raise RuntimeError(f"Resume: could not fetch Google Doc ({doc_id}): {err}")
    return text
