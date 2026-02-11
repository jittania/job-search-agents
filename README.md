## Daily Usage

**Finding/Isolating Job Postings**

1. Save potential jobs to tracker (links and date columns only)

2. Run one command for new rows: archive + metadata + initial fit score - `populatejobs` (or separately: `archivejobs` then `batchfitscore`)

**Applying**

1. Batch generate tailored resume bullets and cover letters with `genbullets today && gencl today`

2. Add company research sources (only for jobs you care about)
   - Create `sources.txt` in job folder
   - Run: `batchsummary`

3. Generate hiring manager outreach drafts
   - `batchhm`

4. Identify jobs needing follow-up (every few days)
   - `followups 10`

---

## Local Commands

- `populatejobs` → For each new row: archive job, infer/fill COMPANY, ROLE TITLE, COMPANY TYPE, COMPANY SIZE BUCKET, ROLE FOCUS, ROLE LEVEL from the job description, run initial fit score, and update the sheet. One command for “new rows only.”

- `archivejobs` → Archive new job postings from tracker only (no metadata or fit score)

- `buildindex` → Generates/refreshes `data/job_index.csv` from the tracker (job_id, company, role title, posting link, archived_at, archive_path).

- `fitjob <job_folder>` → Runs Claude fit scoring + keyword extraction on a single archived job folder and writes `fit.json`.

- `genbullets [today|YYYY-MM-DD]` → Batch: generates tailored resume bullets (`resume_bullets.json`) for all job folders for that day that don’t have them yet. No argument = today. Single job: `genbullets data/<company>/<date>` overwrites `resume_bullets.json` for that folder.

- `gencl [today|YYYY-MM-DD]` → Batch: generates cover letter (`cover_letter.md`) for all job folders for that day that don’t have one yet. No argument = today. Single job: `gencl data/<company>/<date>` overwrites `cover_letter.md` for that folder.

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
- `funnelstats` → Generates a snapshot of job-search funnel metrics (applications, interviews, offers, timing), then writes `data/funnel_stats_<YYYY-MM-DD>.md`.

---

## Skills

✅ Proved you can call a real cloud LLM API (Claude) from Python without leaking secrets

✅ Built a job-ingestion pipeline to archive dynamic web content deterministically (HTML, plaintext, PDF)

✅ Implemented Google Sheets integration to archive new job postings without duplication

✅ Built a durable job index for downstream automation (`job_index.csv` generated from tracker data)

✅ Implemented AI-based JD↔resume fit scoring and keyword extraction, producing structured artifacts (`fit.json`)

✅ Designed and implemented an end-to-end AI-assisted job search automation pipeline in Python

✅ Integrated cloud LLM APIs (Anthropic / Claude) securely using environment variables and virtual environments

✅ Built deterministic ingestion pipelines to archive dynamic web content (HTML, plaintext, PDF) using Playwright and BeautifulSoup

✅ Implemented Google Sheets API integrations for incremental data ingestion, deduplication, and state tracking

✅ Created structured data artifacts for downstream automation (job index, fit scores, keyword extraction, summaries)

✅ Developed AI workflows for resume tailoring, cover letter generation, company research, and outreach drafting

✅ Implemented rules-based analytics and reporting (follow-up detection, application funnel metrics)

✅ Designed CLI tooling and shell aliases for repeatable, low-friction daily workflows

---

## Tools

- Python
- Anthropic / Claude API
- Playwright — headless browser automation for JS-rendered pages + PDF generation
- BeautifulSoup — HTML parsing and text extraction
- Google Sheets API