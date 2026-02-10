## Local Commands

- `archivejobs` → Archive new job postings from tracker (one command)

- `buildindex` → Generates/refreshes `data/job_index.csv` from the tracker (job_id, company, role title, posting link, archived_at, archive_path).

- `fitjob <job_folder>` → Runs Claude fit scoring + keyword extraction on a single archived job folder and writes `fit.json`.


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