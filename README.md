# RoleSynth

## Daily Usage

```
source ~/.zshrc && source .venv/bin/activate && streamlit run ui.py
```

### **Finding/Isolating Job Postings**

1. Save potential jobs to tracker (links and date columns only).

2. Run one command for new rows: `popjobs` (or separately: `archivejobs` then `popjobs` for the rest). Re-run `batchmetadata` as needed (prompts: overwrite all or only rows missing metadata).

        Note: If you get a "token has been expired or revoked" error from a command that uses Google Drive (e.g. `popjobs` / resume Doc fetch), try:
        ```
        cd <path>/job-search-agents
        rm .drive_oauth_token.json
        ```
        then run the command again to trigger browser-based sign-in and write a new token.

3. `fitjob <job_folder>` for single-job fit + keyword extraction (`fit.json`).

### **Applying**

1. `dupres` — batch duplicate base resume; `dupcl` — create blank cover letter docs in Drive.

2. `genbullets && evalskills && evalintroedu` — tailored resume bullets and skills/intro/education recommendations; then `gencl` — cover letters to Drive

3. `batchhm` — hiring manager outreach drafts.

4. Add company research: create `sources.txt` in job folder, then `batchsummary`.

5. `cleanup` (local data); `cleanupres` (Drive)

6. Identify follow-ups with `followups 10`; `funnelstats` for funnel metrics.

7. Single-job: `techstack data/<company>/<date>` for tech stack; `fitjob data/<company>/<date>` for fit scoring.

---

## Local Commands

- `archivejobs` → Archive new job postings from tracker only (no metadata or fit score). **Scripts invoked:** `archive_job` (per row without archived_at).

- `batchhm [YYYY-MM-DD]` → Generates short hiring-manager outreach messages for new archived jobs; skips jobs where `hm_outreach.txt` already exists. **Scripts invoked:** (none).

- `batchmetadata [company]` → Fills or overwrites metadata (company type, company size bucket, role focus, role level) in the sheet. When **company** is provided (e.g. `batchmetadata Costco`), only that company’s rows are processed and the overwrite/new-only prompt is skipped (overwrite is used). Otherwise **prompts: overwrite all existing metadata, or only populate rows that don't have metadata yet** (skips rows that already have company type filled). Resolves each row’s job folder from **company + date applied**, or from a **job_dir** / **archive_path** column when present. **Company type and size:** When multiple LinkedIn companies are found for a row (e.g. "Ditto"), the script pauses and lists up to 4 candidates (with **M for more**); you pick by number, paste a URL, or paste a LinkedIn company URL. The chosen URL is saved in the **COMPANY LINKEDIN PROFILE** column if that column exists; on later runs that URL is reused for that row (no prompt). For the selected profile, company type and size are taken from that LinkedIn page (Playwright). For rows without a saved or selected profile, DDG search + LLM are used. Role title and company name are set at archive time, not by batchmetadata. **Scripts invoked:** `batch_extract_metadata` (per row).

- **Metadata extraction (batch_extract_metadata / batchmetadata):** Company type and company size bucket use the **user-selected LinkedIn profile** when you pick from the multi-company list (employee count and industry are read from that page via Playwright). Otherwise they are derived from DDG search + LLM (employee count → size bucket; rubric for type). Sheet dropdowns should include **UNKNOWN** for company type and company size bucket.

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

        **Scripts invoked:** (none).

- `cleanup` → Deletes `data/<company>/<date>/` folders that no longer have a row in the tracker (e.g. you deleted the row or didn't apply). Use `cleanup --dry-run` to list what would be removed without deleting. **Scripts invoked:** (none).

- `dupcl [YYYY-MM-DD]` → For each job applied on that date (default: today), creates a blank Word document and uploads it to the cover letters Drive folder with the same naming: `YYYY-MM-DD__JittaniaSmith_<Company>_<Position>_CL.docx`. Use `gencl` to fill them with AI-generated cover letters. **Scripts invoked:** (none).

- `dupres [YYYY-MM-DD]` → For each job applied on that date (default: today), copies your resume template Google Doc into the Company Specific Drive folder and renames each copy to `YYYY-MM-DD__JittaniaSmith_<Company>_<Position>` (camelCase). **Scripts invoked:** (none).

**Resume source:** `fitjob`, cover letters, bullets, evalskills, and evalintroedu read your resume from **Google Docs** only. Set `RESUME_GOOGLE_DOC_ID` or `RESUME_GOOGLE_DOC_URL` in `.env` (same OAuth as dupres: `credentials.json` / `.drive_oauth_token.json`). If the Doc can't be fetched, the script exits with an error.

- `evalskills [today|YYYY-MM-DD]` → Batch: for each job from the tracker sheet for that day, evaluates your TECHNICAL SKILLS section for that job and writes `skills_recommendations.json` in the job folder (omit/add recommendations tailored to the JD). No argument = today. Single job: `evalskills data/<company>/<date>` overwrites that folder's `skills_recommendations.json`. **Scripts invoked:** `evaluate_resume_skills_agent` (per job).

- `evalintroedu [today|YYYY-MM-DD]` → Batch: for each job from the tracker sheet for that day, evaluates your resume INTRO (summary paragraph) and EDUCATION section for relevancy to the job and writes `intro_education_recommendations.json` (suggestions to emphasize, trim, or add; per-education-entry relevance). No argument = today. Single job: `evalintroedu data/<company>/<date>`. **Scripts invoked:** `evaluate_intro_education_agent` (per job).

- `fitjob <job_folder>` → Runs Claude fit scoring + keyword extraction on a single archived job folder and writes `fit.json`. **Scripts invoked:** (none).

- `followups [N]` → Identifies applications that need follow-up based on sheet data (includes jobs where `DATE OF OUTCOME` is empty and the applied `DATE` is ≥ N days ago), then writes a Markdown report to `data/followups_<YYYY-MM-DD>.md`. **Scripts invoked:** (none).

- `funnelstats` → Generates a snapshot of job-search funnel metrics (applications, interviews, offers, timing), then writes `data/funnel_stats_<YYYY-MM-DD>.md`. **Scripts invoked:** (none).

- `genbullets [today|YYYY-MM-DD]` → Batch: generates tailored resume bullets (`resume_bullets.json`) for jobs from the tracker sheet for that day (date applied + company), overwriting existing resume_bullets.json if present. No argument = today. Single job: `genbullets data/<company>/<date>` overwrites `resume_bullets.json` for that folder. **Scripts invoked:** `generate_bullets_agent` (per job).

- `gencl [today|YYYY-MM-DD]` → Batch: generates cover letters with Claude and uploads them to the cover letters Drive folder as .docx (same naming as dupcl). No argument = today. Single job: `gencl data/<company>/<date>` generates and uploads (or updates) that job's .docx in Drive. **Scripts invoked:** (none).

- `popjobs`  → For each new row: archive job, infer/fill COMPANY, ROLE TITLE, COMPANY TYPE, COMPANY SIZE BUCKET, ROLE FOCUS, ROLE LEVEL from the job description, and update the sheet. One command for "new rows only." Metadata: company type and company size are **derived from employee count** when available (neutral web search); otherwise UNKNOWN. Sheet dropdowns for company type and company size bucket should include **UNKNOWN**. **Scripts invoked:** `archive_job`, `extract_job_metadata` (per new row).

- `techstack [today|YYYY-MM-DD]` → Batch: infers company tech stack (frontend, backend, infra, databases, tools) from the job description and, if available, by inspecting the first URL in `sources.txt` or a URL you pass. Writes `tech_stack.json` in each job folder. Skips rows where APPLIED VIA ≠ "NOT APPLIED YET" and skips folders that already have `tech_stack.json`. Single job: `techstack data/<company>/<date>` or `techstack data/<company>/<date> <url_to_inspect>`. **Scripts invoked:** `tech_stack_agent` (per job).

**Removed:** Sheet-based **initial fit score** (0–100 column) tooling: `scripts/initial_fit_score_agent.py`, `scripts/batch_initial_fit_score_agent.py` (`batchfitscore`), and `scripts/fit_score_rubric.md`. For per-job fit analysis + keywords, use **`fitjob`** → `fit.json`. Remove any `batchfitscore` alias from your shell config if you still have one.

---

## Skills

✅ Built a job-ingestion pipeline to archive dynamic web content deterministically (HTML, plaintext, PDF)

✅ Implemented Google Sheets integration to archive new job postings without duplication

✅ Implemented AI-based JD↔resume fit scoring and keyword extraction, producing structured artifacts (`fit.json`)

✅ Designed and implemented RoleSynth, an end-to-end AI-assisted pipeline in Python

✅ Added a Streamlit dashboard to run pipeline steps and analytics from the browser instead of the CLI

✅ Integrated cloud LLM APIs (Anthropic / Claude) securely using environment variables and virtual environments

✅ Built deterministic ingestion pipelines to archive dynamic web content (HTML, plaintext, PDF) using Playwright and BeautifulSoup

✅ Implemented Google Sheets API integrations for incremental data ingestion, deduplication, and state tracking

✅ Integrated Google Drive API with OAuth for user-quota file operations (e.g. duplicating resume docs into a folder)

✅ Created structured data artifacts for downstream automation (job index, fit scores, keyword extraction, summaries)

✅ Developed AI workflows for resume tailoring, cover letter generation, company research, and outreach drafting

✅ Implemented rules-based analytics and reporting (follow-up detection, application funnel metrics)

✅ Designed CLI tooling and shell aliases for repeatable, low-friction daily workflows

✅ Added sheet-based batch commands so genbullets and gencl run only for rows still in the tracker (e.g. after deleting low-fit rows)

✅ Added cleanup command to remove orphan `data/` folders when tracker rows are deleted

✅ Implemented resume bullet placement (section, role/project, replace vs append) and robust LLM JSON parsing (markdown stripping, trailing commas)

✅ Handled "posting not found" in archive pipeline with exit codes so batch jobs skip rows instead of failing

---

## Tools

- Python
- Streamlit — web UI to run pipeline steps and analytics from the browser (e.g. `streamlit run ui.py`)
- Anthropic / Claude API
- Playwright — headless browser automation for JS-rendered pages + PDF generation
- BeautifulSoup — HTML parsing and text extraction
- Google Sheets API
- Google Drive API (OAuth for user-quota copies)
- gspread — Google Sheets Python client for tracker read/write
- python-docx — generate and upload cover letter .docx files
- python-dotenv — load `.env` for secrets and config
- Cursor
- Perplexity