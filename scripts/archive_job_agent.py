"""
Fetch a job posting URL with Playwright, extract text and PDF, and save to data/<company>/<date>/
(url.txt, raw.html, job.txt, job.pdf). Infers company from job page if not provided.
Exit 2 if posting not found (e.g. 4xx/5xx or "no longer available"). Used by popjobs and archivejobs.

Invoked by: popjobs, archivejobs (no direct alias).
"""
import os
import sys
from pathlib import Path
from datetime import date

from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")

def clean_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


# Exit code 2 = posting not found / unparseable (for batch to skip row)
POSTING_NOT_FOUND_EXIT = 2


def posting_unavailable(response_status: int | None, text: str) -> bool:
    """True if the page looks like the job is gone or unparseable."""
    if response_status is not None and 400 <= response_status < 600:
        return True
    t = (text or "").strip().lower()
    if len(t) < 150:
        return True
    phrases = (
        "no longer available",
        "has been removed",
        "job has been filled",
        "page not found",
        "this job is no longer",
        "position has been closed",
        "job not found",
        "no longer accepting applications",
    )
    return any(p in t for p in phrases)


def infer_company_and_role_title(job_text: str) -> tuple[str, str]:
    """Use Claude to extract hiring company name and job title from job posting text. Returns (company_name, role_title)."""
    load_dotenv()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = """From the following job posting text, extract exactly two things. Return ONLY these two lines, nothing else:
COMPANY: <the exact name of the company that is hiring, e.g. "Costco" or "Ditto" - use a short, common name when obvious>
ROLE_TITLE: <the exact job title from the posting, e.g. "Senior Software Engineer">

Use short company names where natural (e.g. "Costco" not "Costco Wholesale Corporation"). One line each. If unclear, use "Unknown"."""
    snippet = job_text[:20000].strip()
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=128,
        messages=[{"role": "user", "content": f"{prompt}\n\n{snippet}"}],
    )
    raw = (msg.content[0].text or "").strip()
    company_raw = "Unknown"
    role_title = "Unknown"
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("COMPANY:"):
            company_raw = line.split(":", 1)[1].strip() or "Unknown"
        elif line.upper().startswith("ROLE_TITLE:"):
            role_title = line.split(":", 1)[1].strip() or "Unknown"
    return company_raw or "Unknown", role_title or "Unknown"


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/archive_job_agent.py <url> <date_YYYY-MM-DD>", file=sys.stderr)
        raise SystemExit(1)

    url, folder_date = sys.argv[1], sys.argv[2]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            rendered_html = page.content()
            text = clean_text_from_html(rendered_html)

            status = response.status if response else None
            if posting_unavailable(status, text):
                print("POSTING_NOT_FOUND", file=sys.stderr)
                sys.exit(POSTING_NOT_FOUND_EXIT)

            company_raw, role_title = infer_company_and_role_title(text)
            print(f"COMPANY: {company_raw}", flush=True)
            print(f"ROLE_TITLE: {role_title}", flush=True)

            company = slugify(company_raw)
            out_dir = Path("data") / company / folder_date
            out_dir.mkdir(parents=True, exist_ok=True)

            (out_dir / "url.txt").write_text(url, encoding="utf-8")
            (out_dir / "raw.html").write_text(rendered_html, encoding="utf-8")
            (out_dir / "job.txt").write_text(text, encoding="utf-8")

            try:
                page.pdf(path=str(out_dir / "job.pdf"), format="Letter", print_background=True)
            except Exception as e:
                print(f"⚠️ PDF save failed: {e}")

        finally:
            browser.close()

    print(f"\n⬇️ Saved to {out_dir}\n")

if __name__ == "__main__":
    main()
