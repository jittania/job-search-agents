"""
For each job folder that has sources.txt (URLs), fetch and summarize company/research content
and write a summary. Default: today's job folders; optional arg: YYYY-MM-DD. Creates or updates
summary output in each job folder.

Alias: batchsummary [YYYY-MM-DD]
"""
import os
import sys
from datetime import date
from pathlib import Path

from anthropic import Anthropic
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def read_urls(sources_path: Path) -> list[str]:
    urls = []
    for line in sources_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def iter_job_dirs_for_today(data_dir: Path, day: str):
    # expects data/<company>/<YYYY-MM-DD>/
    for company_dir in data_dir.iterdir():
        if not company_dir.is_dir():
            continue
        day_dir = company_dir / day
        if day_dir.is_dir():
            yield day_dir


def main():
    load_dotenv()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # default: only today's folders
    day = date.today().isoformat()
    if len(sys.argv) == 2:
        # allow: python ... 2026-02-09
        day = sys.argv[1]

    data_dir = Path("data")
    wrote = 0
    skipped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()

            for job_dir in iter_job_dirs_for_today(data_dir, day):
                sources_path = job_dir / "sources.txt"
                out_path = job_dir / "company_summary.md"

                # Only run if user provided sources + no existing summary
                if not sources_path.exists():
                    skipped += 1
                    continue
                if out_path.exists():
                    skipped += 1
                    continue

                urls = read_urls(sources_path)
                if not urls:
                    skipped += 1
                    continue

                # Fetch + extract text from each URL
                blobs = []
                for u in urls:
                    page.goto(u, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                    html = page.content()
                    text = clean_text(html)
                    # cap per-source to keep prompts small
                    text = text[:6000]
                    blobs.append(f"SOURCE URL: {u}\nSOURCE TEXT:\n{text}")

                sources_bundle = "\n\n---\n\n".join(blobs)

                prompt = f"""
                    Create a VERY concise, ADHD-friendly bullet summary based ONLY on the sources below.

                    Output format (use exactly these headers):
                    - What they do
                    - Who they serve / customers
                    - Product / platform clues
                    - Engineering culture signals
                    - Role-relevant talking points (3–5)
                    - Good questions to ask (3)

                    Rules:
                    - Bullet points only
                    - Keep it under ~250–350 words
                    - No fluff, no buzzwords
                    - If something isn’t supported by the sources, say “Unknown”

                    SOURCES:
                    {sources_bundle}
                    """.strip()

                msg = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=800,
                    messages=[{"role": "user", "content": prompt}],
                )

                summary = msg.content[0].text.strip()
                if not summary:
                    print(f"⚠️ Empty output for {job_dir}")
                    continue

                out_path.write_text(summary + "\n", encoding="utf-8")
                wrote += 1
                print(f"\n✅ Wrote {out_path}\n")

        finally:
            browser.close()

    print(f"\nDone. wrote={wrote} skipped={skipped}\n")


if __name__ == "__main__":
    main()