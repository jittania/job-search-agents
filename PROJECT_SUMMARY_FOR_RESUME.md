# Project Summary: RoleSynth (for Resume / ChatGPT)

Use this document to brief ChatGPT (or similar) so it can draft a resume section (e.g. "Personal Project" or "Side Project") that accurately reflects the tech stack and what each tool was used for.

---

## One-paragraph overview

**RoleSynth** is a Python-based pipeline that: (1) reads job links and dates from a **Google Sheets** tracker; (2) **archives** job postings from the web (including JS-rendered pages and PDF snapshots) into a local `data/` tree; (3) uses **Anthropic Claude** to extract metadata (company type, size, role focus, level—with **Playwright**-scraped LinkedIn company pages when the user selects a profile) and to generate tailored resume bullets (with placement: section, role, replace/append), cover letters, and hiring-manager outreach; optional per-job **fit analysis** (e.g. `analyze_fit_agent` → `fit.json`) uses Claude plus structured output; (4) loads the **resume** from a **Google Doc** via **Google Drive API** (OAuth export to plain text) when configured, so cover letters, bullets, eval scripts, and fit analysis use a single source; (5) syncs with **Google Drive** (OAuth) to duplicate resume templates and upload/generate cover letter `.docx` files; and (6) supports optional **company filters** for batch metadata (e.g. `batchmetadata Costco`), analytics (follow-up detection, funnel stats), and cleanup of orphan `data/` folders. **Populate new rows** via `popjobs` (archive + metadata to the sheet; no automated 0–100 “initial fit score” column). All secrets and config are loaded via **python-dotenv** from a `.env` file. The codebase is **Python** scripts under `scripts/`, invoked via shell aliases (e.g. `batchmetadata`, `genbullets today`, `gencl today`, `dupres`, `dupcl`, `cleanup`). Development was done in **Cursor**.

---

## Tool-by-tool: what was used and for what

Every item from the README **Tools** section is listed below with explicit, cited usage.

---

### Python

- **Purpose:** Primary implementation language for the entire project.
- **Where used:** All automation lives in `scripts/*.py`. Python is used for: orchestration (e.g. `populate_jobs.py` runs archive → metadata in sequence via **subprocess**); file and directory handling with **pathlib.Path** (reading/writing `job.txt`, `resume.txt`, `resume_bullets.json`, `fit.json`, CSV job index, Markdown reports); **json** for parsing and emitting LLM responses and structured artifacts; **re** for slugify, trailing-comma fixes in JSON, date patterns; **datetime** for date-applied parsing and report filenames; **shutil** in `cleanup_orphan_job_folders.py` to delete orphan `data/<company>/<date>/` directories; **os** and **sys** for env vars, argv, and exit codes; **io** and **csv** where relevant (e.g. Drive upload streams, job index CSV). No other language is used for the core pipeline.

---

### Anthropic / Claude API

- **Purpose:** All LLM-based behavior (extraction, scoring, generation).
- **Where used:**  
  - **archive_job_agent.py** — Claude is used once per job to infer company name from job text when not provided (Haiku, short prompt).
  - **batch_extract_metadata.py** — Claude returns structured JSON (company_type, company_size_bucket, role_focus, role_level) from job description and optional DDG search; when the user selects a LinkedIn company profile, company type and size are taken from that page (scraped with Playwright) instead. **extract_job_metadata_agent.py** is the single-job entry point that delegates to `batch_extract_metadata.extract_metadata_for_job_dir`.
  - **analyze_fit_agent.py** — Fit analysis + keyword extraction, writes `fit.json` (resume from **resume_loader** when configured).  
  - **generate_bullets_agent.py** — Claude generates tailored resume bullets (with placement: section, role/project, replace vs append) and returns JSON; output is written to `resume_bullets.json`. Resume text is from **resume_loader** (Google Doc).
  - **batch_generate_cover_letter_agent.py** / **generate_cover_letter_agent.py** — Claude writes cover letter text; batch script then turns it into `.docx` and uploads to Drive. Resume text is from **resume_loader**.
  - **batch_generate_hm_outreach_agent.py** — Claude drafts short hiring-manager outreach messages. Resume from **resume_loader**.
  - **evaluate_resume_skills_agent.py** / **evaluate_intro_education_agent.py** — Claude evaluates TECHNICAL SKILLS or INTRO/EDUCATION for a job; resume from **resume_loader**.
  API key is always loaded from the environment (via **python-dotenv**); never hardcoded.

---

### Playwright

- **Purpose:** Headless browser automation for JS-rendered job pages and PDF capture.
- **Where used:**  
  - **archive_job_agent.py** — `sync_playwright()`, Chromium launch, `page.goto(url)`, `page.wait_for_timeout`, `page.content()` to get fully rendered HTML; then **BeautifulSoup** is used to strip scripts/styles and extract plain text into `job.txt`. Same script uses `page.pdf()` to save a Letter-format PDF of the job page to `job.pdf` in the job folder (with print_background=True). Response status is checked to detect 4xx/5xx and trigger "posting not found" exit code for batch.  
  - **batch_extract_metadata.py** — Playwright loads LinkedIn company pages (when the user selects a profile); the script parses the About section (e.g. `data-test-id="about-us__size"`) for employee count and industry so company type and size come from the Doc instead of the face-pile "Discover all N employees" link.  
  So: Playwright is used for (1) fetching and rendering job posting URLs, (2) saving job pages as PDFs, and (3) scraping LinkedIn company pages for metadata.

---

### BeautifulSoup

- **Purpose:** HTML parsing and text extraction from raw or rendered HTML.
- **Where used:**  
  - **archive_job_agent.py** — `BeautifulSoup(html, "html.parser")`; scripts, styles, and noscript are removed, then `get_text(separator=" ")` is used to produce clean plain text written to `job.txt`.  
  So: BeautifulSoup is used wherever we need to turn HTML (from Playwright or otherwise) into clean text for storage or for LLM input.

---

### Google Sheets API

- **Purpose:** Single source of truth for the job tracker (links, dates, company, role, metadata, optional columns such as initial fit score / outcomes).
- **Where used:** All sheet access is done via **gspread** (the Python client for Google Sheets API). The tracker is read and written through gspread in: **populate_jobs.py** (new rows: write COMPANY, ROLE TITLE, metadata columns, archived_at, archive path); **batch_archive_from_sheet.py** (read rows without archived_at, trigger archive per row); **batch_extract_metadata.py** (read rows for metadata extraction, optional company filter; write company type, size bucket, role focus, level, and optionally COMPANY LINKEDIN PROFILE); **batch_generate_bullets_agent.py** (read rows by date applied + company to get job dirs); **batch_generate_cover_letter_agent.py** (same: date applied + company + role title for naming and job dirs); **duplicate_resume_docs.py** and **duplicate_cover_letter_docs.py** (read date applied + company + role for today/target date to duplicate docs); **cleanup_orphan_job_folders.py** (read all rows with date applied + company to build "keep" set for data/ folders); **identify_followups.py** (read sheet for outcomes and dates); **funnel_stats.py** (read sheet for funnel metrics). So the **Google Sheets API** (via gspread) is used for: incremental ingestion, deduplication, state tracking, and driving which jobs get archived, scored, metadata-filled, bulleted, covered, duplicated, and which folders are kept or cleaned up.

---

### Google Drive API

- **Purpose:** Create and update files in the user’s Drive (resume copies, cover letter folder) using the user’s quota via OAuth.
- **Where used:**  
  - **resume_loader.py** — Uses **google-api-python-client** with **OAuth** (same credentials as dupres). Calls `drive.files().export_media(fileId=doc_id, mimeType="text/plain")` to export the user's resume Google Doc as plain text. Used by fit analysis (`analyze_fit_agent` / `fitjob`), cover letters, bullets, evalskills, and evalintroedu so the resume is a single source (no local `resume.txt`). Requires `RESUME_GOOGLE_DOC_ID` or `RESUME_GOOGLE_DOC_URL` in `.env`.  
  - **duplicate_resume_docs.py** — Uses **google-api-python-client** (`build("drive", "v3", credentials=...)`) with **OAuth** credentials (from **google_auth_oauthlib** flow and **google.oauth2.credentials**). Copies a template Google Doc (by ID) into a "Company Specific" Drive folder for each row from the sheet for the target date; renames copies to `YYYY-MM-DD__JittaniaSmith_<Company>_<Position>`.  
  - **duplicate_cover_letter_docs.py** — Same OAuth Drive client; creates blank Word documents (generated with **python-docx**) and uploads them via `drive.files().create()` with `MediaIoBaseUpload` to the cover letters folder.  
  - **batch_generate_cover_letter_agent.py** — Same Drive client (OAuth); after Claude generates cover letter text, the script builds a `.docx` with python-docx and uploads/updates the file in the cover letters folder by name (create or update).  
  So: **Google Drive API** is used with **OAuth** for: (1) exporting the resume Google Doc as plain text for all resume-consuming scripts, (2) copying the resume template into a company-specific folder, (3) creating blank cover letter docs, and (4) uploading/updating AI-generated cover letter `.docx` files—all against the user’s quota.

---

### gspread

- **Purpose:** Python client for the Google Sheets API; used for all tracker read/write.
- **Where used:** Every script that touches the tracker uses `gspread`: typically `gspread.service_account(filename=sa_json)` then `gc.open_by_key(sheet_id).worksheet(worksheet_name)`, then `get_all_values()`, `row_values(1)` for headers, `update_cell()`, etc. Used in: **populate_jobs.py**, **batch_archive_from_sheet.py**, **batch_extract_metadata.py**, **batch_generate_bullets_agent.py**, **batch_generate_cover_letter_agent.py**, **duplicate_resume_docs.py**, **duplicate_cover_letter_docs.py**, **cleanup_orphan_job_folders.py**, **identify_followups.py**, **funnel_stats.py**. So **gspread** is the concrete library that implements "Google Sheets API" usage for tracker read/write throughout the project.

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
- **Where used:** Essentially every script that needs config or secrets calls `load_dotenv()` (from **python-dotenv**) and then reads `os.environ["ANTHROPIC_API_KEY"]`, `os.environ["GOOGLE_SA_JSON"]`, `os.environ["SHEET_ID"]`, `os.environ["WORKSHEET_NAME"]`, `os.environ.get("DRIVE_COVER_LETTERS_FOLDER_ID")`, `os.environ.get("DRIVE_COMPANY_SPECIFIC_FOLDER_ID")`, `os.environ.get("DRIVE_CREDENTIALS_JSON")`, `os.environ.get("RESUME_GOOGLE_DOC_ID")` / `os.environ.get("RESUME_GOOGLE_DOC_URL")`, etc. Used in: **archive_job_agent.py**, **populate_jobs.py**, **batch_archive_from_sheet.py**, **batch_extract_metadata.py**, **extract_job_metadata_agent.py**, **resume_loader.py**, **generate_bullets_agent.py**, **batch_generate_bullets_agent.py**, **batch_generate_cover_letter_agent.py**, **generate_cover_letter_agent.py**, **duplicate_resume_docs.py**, **duplicate_cover_letter_docs.py**, **cleanup_orphan_job_folders.py**, **identify_followups.py**, **funnel_stats.py**, **analyze_fit_agent.py**, **batch_generate_hm_outreach_agent.py**, **evaluate_resume_skills_agent.py**, **evaluate_intro_education_agent.py**. So **python-dotenv** is used to load `.env` for secrets and config in every script that touches APIs or sheet/Drive IDs.

---

### Cursor

- **Purpose:** IDE used for development and editing.
- **Where used:** RoleSynth was developed and maintained in Cursor (editor/environment). No runtime dependency; only noted so the resume can accurately say the project was built using Cursor if desired.

---

## Optional extra detail for ChatGPT

- **Structured outputs:** The pipeline produces and consumes JSON (e.g. `fit.json`, `resume_bullets.json` with placement, metadata from batch_extract_metadata). LLM JSON is often wrapped in markdown or has trailing commas; the code strips markdown code fences and normalizes trailing commas before `json.loads`.
- **Resume from Google Doc:** When `RESUME_GOOGLE_DOC_ID` or `RESUME_GOOGLE_DOC_URL` is set in `.env`, **resume_loader.py** fetches the resume as plain text via the Drive API (OAuth, same as dupres). Fit analysis (`fitjob`), cover letters, bullets, evalskills, and evalintroedu all use this; there is no local `resume.txt` fallback.
- **Batch vs single-job / company filter:** Many commands support "batch by date" (e.g. all jobs for today from the sheet) and "single job" (e.g. `genbullets data/company/2026-02-16`). **batchmetadata** accepts an optional company name (e.g. `batchmetadata Costco`) to process only rows matching that company and skip the overwrite/new-only prompt (overwrite is used). Cleanup is driven by the set of (company, date) still present in the sheet.
- **Exit codes:** The archive script exits with code 2 when the posting is unavailable (e.g. 4xx/5xx or "job no longer available" text); the populate script catches this and skips the row instead of failing the whole run.

You can hand this file to ChatGPT and ask it to write a concise resume bullet or short paragraph that highlights RoleSynth and cites the tools accurately.
