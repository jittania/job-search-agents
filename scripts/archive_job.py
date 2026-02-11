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


def infer_company_from_job_text(job_text: str) -> str:
    """Use Claude to extract the hiring company name from job posting text."""
    load_dotenv()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = """From the following job posting text, extract only the name of the company that is hiring for this position. Return nothing but the company name, one line, no explanation. If you cannot determine the company, return "Unknown"."""
    snippet = job_text[:20000].strip()
    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=64,
        messages=[{"role": "user", "content": f"{prompt}\n\n{snippet}"}],
    )
    name = (msg.content[0].text or "").strip()
    return name or "Unknown"


def main():
    # 3 args: url, date_applied → infer company from job page
    # 4 args: company, url, date_applied → use provided company
    if len(sys.argv) not in (3, 4):
        print("Usage: python scripts/archive_job.py <url> <date_YYYY-MM-DD>  OR  <company> <url> <date_YYYY-MM-DD>", file=sys.stderr)
        raise SystemExit(1)

    if len(sys.argv) == 3:
        url, folder_date = sys.argv[1], sys.argv[2]
        company_raw = None
    else:
        company_raw = sys.argv[1]
        url = sys.argv[2]
        folder_date = sys.argv[3]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            rendered_html = page.content()
            text = clean_text_from_html(rendered_html)

            if company_raw is None:
                company_raw = infer_company_from_job_text(text)
                # So batch script can write back to sheet
                print(f"COMPANY: {company_raw}", flush=True)

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