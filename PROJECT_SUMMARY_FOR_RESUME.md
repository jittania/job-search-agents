# Project Summary: Job Search Automation (for Resume / ChatGPT)

Use this document to brief ChatGPT (or similar) so it can draft a resume section (e.g. "Personal Project" or "Side Project") that accurately reflects the tech stack and what each tool was used for.

---

## One-paragraph overview

This project is a **Python-based job-search automation pipeline** that: (1) reads job links and dates from a **Google Sheets** tracker; (2) **archives** job postings from the web (including JS-rendered pages and PDF snapshots) into a local `data/` tree; (3) uses **Anthropic Claude** to extract metadata (company, role title, company type, size, focus, level), run initial fit scoring (JD ↔ resume), and generate tailored resume bullets (with placement: section, role, replace/append), cover letters, company summaries, and hiring-manager outreach; (4) syncs with **Google Drive** (OAuth) to duplicate resume templates and upload/generate cover letter `.docx` files; and (5) supports analytics (follow-up detection, funnel stats) and cleanup of orphan `data/` folders when tracker rows are removed. All secrets and config (API keys, sheet ID, Drive folder IDs) are loaded via **python-dotenv** from a `.env` file. The codebase is structured as **Python** scripts under `scripts/`, invoked via shell aliases (e.g. `populatejobs`, `genbullets today`, `gencl today`, `dupres`, `dupcl`, `cleanup`). Development was done in **Cursor**.

---

## Tool-by-tool: what was used and for what

Every item from the README **Tools** section is listed below with explicit, cited usage.

---

### Python

- **Purpose:** Primary implementation language for the entire project.
- **Where used:** All automation lives in `scripts/*.py`. Python is used for: orchestration (e.g. `populate_jobs.py` runs archive → metadata → fit score in sequence via **subprocess**); file and directory handling with **pathlib.Path** (reading/writing `job.txt`, `resume.txt`, `resume_bullets.json`, `fit.json`, CSV job index, Markdown reports); **json** for parsing and emitting LLM responses and structured artifacts; **re** for slugify, trailing-comma fixes in JSON, date patterns; **datetime** for date-applied parsing and report filenames; **shutil** in `cleanup_orphan_job_folders.py` to delete orphan `data/<company>/<date>/` directories; **os** and **sys** for env vars, argv, and exit codes; **io** and **csv** where relevant (e.g. Drive upload streams, job index CSV). No other language is used for the core pipeline.

---

### Anthropic / Claude API

- **Purpose:** All LLM-based behavior (extraction, scoring, generation).
- **Where used:**  
  - **archive_job_agent.py** — Claude is used once per job to infer company name from job text when not provided (Haiku, short prompt).
  - **extract_job_metadata_agent.py** — Claude returns structured JSON (role_title, company_type, company_size_bucket, role_focus, role_level) from job description.
  - **initial_fit_score_agent.py** — Claude scores resume–job fit 0–100 with a conservative rubric and returns `fit_score_0_to_100`.  
  - **analyze_fit_agent.py** — Deeper fit analysis + keyword extraction, writes `fit.json`.  
  - **generate_bullets_agent.py** — Claude generates tailored resume bullets (with placement: section, role/project, replace vs append) and returns JSON; output is written to `resume_bullets.json`.  
  - **batch_generate_cover_letter_agent.py** / **generate_cover_letter_agent.py** — Claude writes cover letter text; batch script then turns it into `.docx` and uploads to Drive.  
  - **batch_generate_hm_outreach_agent.py** — Claude drafts short hiring-manager outreach messages.  
  API key is always loaded from the environment (via **python-dotenv**); never hardcoded.

---

### Playwright

- **Purpose:** Headless browser automation for JS-rendered job pages and PDF capture.
- **Where used:**  
  - **archive_job_agent.py** — `sync_playwright()`, Chromium launch, `page.goto(url)`, `page.wait_for_timeout`, `page.content()` to get fully rendered HTML; then **BeautifulSoup** is used to strip scripts/styles and extract plain text into `job.txt`. Same script uses `page.pdf()` to save a Letter-format PDF of the job page to `job.pdf` in the job folder (with print_background=True). Response status is checked to detect 4xx/5xx and trigger "posting not found" exit code for batch.  
  So: Playwright is used for (1) fetching and rendering job posting URLs and (2) saving job pages as PDFs.

---

### BeautifulSoup

- **Purpose:** HTML parsing and text extraction from raw or rendered HTML.
- **Where used:**  
  - **archive_job_agent.py** — `BeautifulSoup(html, "html.parser")`; scripts, styles, and noscript are removed, then `get_text(separator=" ")` is used to produce clean plain text written to `job.txt`.  
  So: BeautifulSoup is used wherever we need to turn HTML (from Playwright or otherwise) into clean text for storage or for LLM input.

---

### Google Sheets API

- **Purpose:** Single source of truth for the job tracker (links, dates, company, role, metadata, fit score, outcomes).
- **Where used:** All sheet access is done via **gspread** (the Python client for Google Sheets API). So "Google Sheets API" here means: the tracker spreadsheet is read and written through gspread in: **populate_jobs.py** (new rows: write COMPANY, ROLE TITLE, metadata columns, initial fit score, archived_at, archive path); **batch_archive_from_sheet.py** (read rows without archived_at, trigger archive per row); **batch_initial_fit_score_agent.py** (read rows missing initial fit score, write score); **batch_generate_bullets_agent.py** (read rows by date applied + company to get job dirs from sheet); **batch_generate_cover_letter_agent.py** (same: date applied + company + role title for naming and job dirs); **duplicate_resume_docs.py** and **duplicate_cover_letter_docs.py** (read date applied + company + role for today/target date to duplicate docs); **cleanup_orphan_job_folders.py** (read all rows with date applied + company to build "keep" set for data/ folders); **identify_followups.py** (read sheet for outcomes and dates); **funnel_stats.py** (read sheet for funnel metrics); **build_job_index_from_sheet.py** (read tracker to build `data/job_index.csv`). So the **Google Sheets API** (via gspread) is used for: incremental ingestion, deduplication, state tracking, and driving which jobs get archived, scored, bulleted, covered, duplicated, and which folders are kept or cleaned up.

---

### Google Drive API

- **Purpose:** Create and update files in the user’s Drive (resume copies, cover letter folder) using the user’s quota via OAuth.
- **Where used:**  
  - **duplicate_resume_docs.py** — Uses **google-api-python-client** (`build("drive", "v3", credentials=...)`) with **OAuth** credentials (from **google_auth_oauthlib** flow and **google.oauth2.credentials**). Copies a template Google Doc (by ID) into a "Company Specific" Drive folder for each row from the sheet for the target date; renames copies to `YYYY-MM-DD__JittaniaSmith_<Company>_<Position>`.  
  - **duplicate_cover_letter_docs.py** — Same OAuth Drive client; creates blank Word documents (generated with **python-docx**) and uploads them via `drive.files().create()` with `MediaIoBaseUpload` to the cover letters folder.  
  - **batch_generate_cover_letter_agent.py** — Same Drive client (OAuth); after Claude generates cover letter text, the script builds a `.docx` with python-docx and uploads/updates the file in the cover letters folder by name (create or update).  
  So: **Google Drive API** is used with **OAuth** for: (1) copying the resume template into a company-specific folder, (2) creating blank cover letter docs, and (3) uploading/updating AI-generated cover letter `.docx` files—all against the user’s quota, not a service account’s.

---

### gspread

- **Purpose:** Python client for the Google Sheets API; used for all tracker read/write.
- **Where used:** Every script that touches the tracker uses `gspread`: typically `gspread.service_account(filename=sa_json)` then `gc.open_by_key(sheet_id).worksheet(worksheet_name)`, then `get_all_values()`, `row_values(1)` for headers, `update_cell()`, etc. Used in: **populate_jobs.py**, **batch_archive_from_sheet.py**, **batch_initial_fit_score_agent.py**, **batch_generate_bullets_agent.py**, **batch_generate_cover_letter_agent.py**, **duplicate_resume_docs.py**, **duplicate_cover_letter_docs.py**, **cleanup_orphan_job_folders.py**, **identify_followups.py**, **funnel_stats.py**. So **gspread** is the concrete library that implements "Google Sheets API" usage for tracker read/write throughout the project.

---

### python-docx

- **Purpose:** Generate and manipulate Word (`.docx`) documents programmatically.
- **Where used:**  
  - **duplicate_cover_letter_docs.py** — Builds a blank Document with `Document()`, then exports to bytes and uploads to Drive so each job has a placeholder cover letter file.  
  - **batch_generate_cover_letter_agent.py** — After Claude returns plain-text cover letter content, the script creates a `Document()`, adds paragraphs from the text, saves to a bytes buffer, and uploads that as the job’s cover letter `.docx` (create or update by name in the Drive folder).  
  So: **python-docx** is used to (1) create blank cover letter docs for dupcl and (2) turn Claude-generated cover letter text into the final `.docx` files that are uploaded to Google Drive.

---

### python-dotenv

- **Purpose:** Load environment variables from a `.env` file so API keys and config are not hardcoded.
- **Where used:** Essentially every script that needs config or secrets calls `load_dotenv()` (from **python-dotenv**) and then reads `os.environ["ANTHROPIC_API_KEY"]`, `os.environ["GOOGLE_SA_JSON"]`, `os.environ["SHEET_ID"]`, `os.environ["WORKSHEET_NAME"]`, `os.environ.get("DRIVE_COVER_LETTERS_FOLDER_ID")`, `os.environ.get("DRIVE_COMPANY_SPECIFIC_FOLDER_ID")`, `os.environ.get("DRIVE_CREDENTIALS_JSON")`, etc. Used in: **archive_job_agent.py**, **populate_jobs.py**, **batch_archive_from_sheet.py**, **extract_job_metadata_agent.py**, **initial_fit_score_agent.py**, **batch_initial_fit_score_agent.py**, **generate_bullets_agent.py**, **batch_generate_bullets_agent.py**, **batch_generate_cover_letter_agent.py**, **generate_cover_letter_agent.py**, **duplicate_resume_docs.py**, **duplicate_cover_letter_docs.py**, **cleanup_orphan_job_folders.py**, **identify_followups.py**, **funnel_stats.py**, **analyze_fit_agent.py**, **batch_generate_hm_outreach_agent.py**. So **python-dotenv** is used to load `.env` for secrets and config in every script that touches APIs or sheet/Drive IDs.

---

### Cursor

- **Purpose:** IDE used for development and editing.
- **Where used:** The project was developed and maintained in Cursor (editor/environment). No runtime dependency; only noted so the resume can accurately say the project was built using Cursor if desired.

---

## Optional extra detail for ChatGPT

- **Structured outputs:** The pipeline produces and consumes JSON (e.g. `fit.json`, `resume_bullets.json` with placement, metadata from extract_job_metadata_agent). LLM JSON is often wrapped in markdown or has trailing commas; the code strips markdown code fences and normalizes trailing commas before `json.loads`.
- **Batch vs single-job:** Many commands support both "batch by date" (e.g. all jobs for today from the sheet) and "single job" (e.g. `genbullets data/company/2026-02-16`). Batch behavior is driven by the sheet (date applied + company); cleanup is driven by the set of (company, date) still present in the sheet.
- **Exit codes:** The archive script exits with code 2 when the posting is unavailable (e.g. 4xx/5xx or "job no longer available" text); the populate script catches this and skips the row instead of failing the whole run.

You can hand this file to ChatGPT and ask it to write a concise resume bullet or short paragraph that highlights the project and cites the tools accurately.
