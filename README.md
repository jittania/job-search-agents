## Local Commands

- `archivejobs` → Archive new job postings from tracker (one command)

- `buildindex` → Generates/refreshes `data/job_index.csv` from the tracker (job_id, company, role title, posting link, archived_at, archive_path).

- `fitjob <job_folder>` → Runs Claude fit scoring + keyword extraction on a single archived job folder and writes `fit.json`.

- `genbullets data/<company>/<date>` → Generates tailored, job-specific resume bullets using the archived job description and base resume, writing `resume_bullets.json`.

- `gencl <job_folder>`
→ Generates a single, job-specific cover letter (`cover_letter.md`) using the archived job description and base resume; and refuses to overwrite if a cover letter already exists.

- `batchsummary` →

        For each new job you want summarized, create sources.txt

        ```
        touch data/costco/2026-02-09/sources.txt
        ```

        Put URLs in it (one per line), e.g.

        ```
        https://www.costco.com/
        https://careers.costco.com/
        ```

        Run batch for today

        ```
        batchsummary
        ```

        Or for a specific date folder:

        ```
        batchsummary 2026-02-09
        ```

- `batchhm [YYYY-MM-DD]` → Generates short hiring-manager outreach messages for new archived jobs; skips jobs where `hm_outreach.txt` already exists.
- `followups [N]` → Identifies applications that need follow-up based on sheet data (includes jobs where `DATE OF OUTCOME` is empty and the applied `DATE` is ≥ N days ago), then writes a Markdown report to `data/followups_<YYYY-MM-DD>.md`.

## Skills

✅ Proved you can call a real cloud LLM API (Claude) from Python without leaking secrets

✅ Built a job-ingestion pipeline to archive dynamic web content deterministically (HTML, plaintext, PDF)

✅ Implemented Google Sheets integration to archive new job postings without duplication

✅ Built a durable job index for downstream automation (`job_index.csv` generated from tracker data)

✅ Implemented AI-based JD↔resume fit scoring and keyword extraction, producing structured artifacts (`fit.json`)


## Tools

- Python
- Anthropic / Claude API
- Playwright — headless browser automation for JS-rendered pages + PDF generation
- BeautifulSoup — HTML parsing and text extraction
- Google Sheets API