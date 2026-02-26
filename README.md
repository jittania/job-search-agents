# TBD Name: RoleSynth

## Daily Usage

```
source ~/.zshrc && source .venv/bin/activate
```

### **Finding/Isolating Job Postings**

1. Save potential jobs to tracker (links and date columns only).

2. Just use `archivejobs` for now ~~Run one command for new rows: `popjobs` (or separately: `archivejobs` then `batchfitscore`). Re-run `batchfitscore` or `batchmetadata` as needed (each prompts: overwrite all or new only).~~

3. ~~`fitjob <job_folder>` for single-job fit + keyword extraction (`fit.json`).~~

### **Applying**

1. `dupres` — batch duplicate base resume; `dupcl` — create blank cover letter docs in Drive.

~~2. `genbullets && evalskills && evalintroedu` — tailored resume bullets and skills/intro/education recommendations; then `gencl` — cover letters to Drive~~

~~3. `batchhm` — hiring manager outreach drafts.~~

~~4. Add company research: create `sources.txt` in job folder, then `batchsummary`.~~

5. `cleanup` (local data); ~~`cleanupres` (Drive)~~

~~6. Identify follow-ups with `followups 10`; `funnelstats` for funnel metrics.~~

~~7. Single-job: `techstack data/<company>/<date>` for tech stack; `fitjob data/<company>/<date>` for fit scoring.~~

---

## In Progress/Need Re-working

- Base resume - can this be pulled/read from Drive instead
- `batchfitscore`
- `batchmetadata`
- `genbullets`
- `evalskills`
- `evalintroedu`
- `gencl`
- `batchhm`
- `batchsummary`
- `cleanup_orphan_drive_resumes`
- `batch_tech_stack_agent`
- `fitjob <job_folder>`

---

## Local Commands

- `archivejobs` → Archive new job postings from tracker only (no metadata or fit score). **Scripts invoked:** `archive_job` (per row without archived_at).

- `batchfitscore` → Fills or overwrites initial fit score (0–100) in the sheet. Prompts: overwrite all or new only. **Scoring is deterministic:** LLM extracts structured requirements only; Python computes subscores from rules (must-have = literal substring of resume text or synonym; no semantic match). Hard assertions: job and resume ≥500 chars or fail; each row logs job_path, job_hash, resume_path, resume_hash and first 300 chars (stderr); self-checks fail if "matched" term not in resume or if product company has HL7/C#/.NET in must_have (wrong job file). Optional: if the sheet has a **job_dir** or **archive_path** column, that path is used for the job folder (unique dir per job); otherwise path is derived from company + date. See `scripts/fit_score_constants.py`. **Scripts invoked:** `initial_fit_score_agent` (per row; it runs `check_security_clearance` before scoring; clearance-required rows get "N/A (clearance)").

- `batchhm [YYYY-MM-DD]` → Generates short hiring-manager outreach messages for new archived jobs; skips jobs where `hm_outreach.txt` already exists. **Scripts invoked:** (none).

- `batchmetadata` → Fills or overwrites metadata (role title, company type, company size bucket, role focus, role level) in the sheet. **Prompts: overwrite all existing metadata, or only populate rows that don't have metadata yet** (skips rows that already have company type filled). Uses same job_dir logic as batchfitscore. **Single-job `extract_job_metadata.py` only outputs JSON**—it does not write to the sheet; only popjobs and batchmetadata write metadata to the sheet. **Scripts invoked:** `extract_job_metadata` (per row).

- **Metadata extraction (extract_job_metadata / batchmetadata):** Company type and company size bucket are derived from **employee count** when the LLM or search finds it (&lt;50→STARTUP, 50–199→STARTUP, 200–999→SCALE-UP, 1000+→SCALE-UP; &gt;200 never STARTUP). If unknown, both default to **UNKNOWN** (no bias to STARTUP or 1000+). Web search uses neutral queries (employee count, headcount, LinkedIn). Add UNKNOWN to your sheet dropdowns for company type and company size bucket.

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

- `evalskills [today|YYYY-MM-DD]` → Batch: for each job from the tracker sheet for that day, evaluates your TECHNICAL SKILLS section for that job and writes `skills_recommendations.json` in the job folder (omit/add recommendations tailored to the JD). No argument = today. Single job: `evalskills data/<company>/<date>` overwrites that folder's `skills_recommendations.json`. **Scripts invoked:** `evaluate_resume_skills_agent` (per job).

- `evalintroedu [today|YYYY-MM-DD]` → Batch: for each job from the tracker sheet for that day, evaluates your resume INTRO (summary paragraph) and EDUCATION section for relevancy to the job and writes `intro_education_recommendations.json` (suggestions to emphasize, trim, or add; per-education-entry relevance). No argument = today. Single job: `evalintroedu data/<company>/<date>`. **Scripts invoked:** `evaluate_intro_education_agent` (per job).

- `fitjob <job_folder>` → Runs Claude fit scoring + keyword extraction on a single archived job folder and writes `fit.json`. **Scripts invoked:** (none).

- `followups [N]` → Identifies applications that need follow-up based on sheet data (includes jobs where `DATE OF OUTCOME` is empty and the applied `DATE` is ≥ N days ago), then writes a Markdown report to `data/followups_<YYYY-MM-DD>.md`. **Scripts invoked:** (none).

- `funnelstats` → Generates a snapshot of job-search funnel metrics (applications, interviews, offers, timing), then writes `data/funnel_stats_<YYYY-MM-DD>.md`. **Scripts invoked:** (none).

- `genbullets [today|YYYY-MM-DD]` → Batch: generates tailored resume bullets (`resume_bullets.json`) for jobs from the tracker sheet for that day (date applied + company), overwriting existing resume_bullets.json if present. No argument = today. Single job: `genbullets data/<company>/<date>` overwrites `resume_bullets.json` for that folder. **Scripts invoked:** `generate_bullets_agent` (per job).

- `gencl [today|YYYY-MM-DD]` → Batch: generates cover letters with Claude and uploads them to the cover letters Drive folder as .docx (same naming as dupcl). No argument = today. Single job: `gencl data/<company>/<date>` generates and uploads (or updates) that job's .docx in Drive. **Scripts invoked:** (none).

- `popjobs`  → For each new row: archive job, infer/fill COMPANY, ROLE TITLE, COMPANY TYPE, COMPANY SIZE BUCKET, ROLE FOCUS, ROLE LEVEL from the job description, run initial fit score, and update the sheet. One command for "new rows only." Metadata: company type and company size are **derived from employee count** when available (neutral web search); otherwise UNKNOWN. Sheet dropdowns for company type and company size bucket should include **UNKNOWN**. **Scripts invoked:** `archive_job`, `check_security_clearance`, `extract_job_metadata`, `initial_fit_score_agent` (per new row).

- `techstack [today|YYYY-MM-DD]` → Batch: infers company tech stack (frontend, backend, infra, databases, tools) from the job description and, if available, by inspecting the first URL in `sources.txt` or a URL you pass. Writes `tech_stack.json` in each job folder. Skips rows where APPLIED VIA ≠ "NOT APPLIED YET" and skips folders that already have `tech_stack.json`. Single job: `techstack data/<company>/<date>` or `techstack data/<company>/<date> <url_to_inspect>`. **Scripts invoked:** `tech_stack_agent` (per job).

---

## Skills

✅ Built a job-ingestion pipeline to archive dynamic web content deterministically (HTML, plaintext, PDF)

✅ Implemented Google Sheets integration to archive new job postings without duplication

✅ Implemented AI-based JD↔resume fit scoring and keyword extraction, producing structured artifacts (`fit.json`)

✅ Designed and implemented an end-to-end AI-assisted job search automation pipeline in Python

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
- Anthropic / Claude API
- Playwright — headless browser automation for JS-rendered pages + PDF generation
- BeautifulSoup — HTML parsing and text extraction
- Google Sheets API
- Google Drive API (OAuth for user-quota copies)
- gspread — Google Sheets Python client for tracker read/write
- python-docx — generate and upload cover letter .docx files
- python-dotenv — load `.env` for secrets and config
- Cursor