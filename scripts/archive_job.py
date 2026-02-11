import sys
from pathlib import Path
from datetime import date

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def slugify(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")

def clean_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())

def main():
    if len(sys.argv) not in (3, 4):
        print("Usage: python scripts/archive_job.py <company> <url> [date_applied_YYYY-MM-DD]")
        raise SystemExit(1)

    company = slugify(sys.argv[1])
    url = sys.argv[2]
    folder_date = sys.argv[3] if len(sys.argv) == 4 else date.today().isoformat()

    out_dir = Path("data") / company / folder_date
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "url.txt").write_text(url, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Give JS-rendered pages a moment to hydrate.
            # (Later we can replace this with a site-specific selector wait.)
            page.wait_for_timeout(3000)

            # Rendered HTML (this is the key difference vs requests)
            rendered_html = page.content()
            (out_dir / "raw.html").write_text(rendered_html, encoding="utf-8")

            # Clean text from rendered HTML
            text = clean_text_from_html(rendered_html)
            (out_dir / "job.txt").write_text(text, encoding="utf-8")

            # Best-effort PDF
            try:
                page.pdf(path=str(out_dir / "job.pdf"), format="Letter", print_background=True)
            except Exception as e:
                print(f"⚠️ PDF save failed: {e}")

        finally:
            browser.close()

    print(f"\n⬇️ Saved to {out_dir}\n")

if __name__ == "__main__":
    main()