"""
RoleSynth — Streamlit UI for the job search automation pipeline.
Run: streamlit run ui.py
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Project root and .env
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_cmd(script_path: Path, args: list, stdin_text: str | None) -> tuple[int, str, str]:
    """Run a Python script; return (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(script_path)] + args
    env = os.environ.copy()
    r = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
        input=stdin_text,
    )
    return r.returncode, r.stdout or "", r.stderr or ""


def _pipe_button(label: str, script_path: Path, args: list, stdin_text: str | None, desc: str | None = None):
    """Render a single pipeline button and run command on click; show output."""
    if not script_path.exists():
        st.error(f"Script not found: {script_path}")
        return
    key = f"pipe_{label}"
    if desc:
        c1, c2 = st.columns([1, 8])
        with c1:
            clicked = st.button(label, key=key)
        with c2:
            st.caption(desc)
    else:
        clicked = st.button(label, key=key)
    if clicked:
        st.info("This may take several minutes depending on the number of rows.")
        with st.spinner(f"Running {label}…"):
            code, out, err = run_cmd(script_path, args, stdin_text)
        if code != 0:
            st.error(f"**{label}** failed (exit code {code})")
            if err:
                st.code(err, language="text")
            if out:
                st.code(out, language="text")
        else:
            st.success(f"**{label}** completed.")
            combined = (out.strip() + "\n\n" + err.strip()).strip()
            if combined:
                st.code(combined, language="text")


def page_pipeline():
    st.header("Pipeline")
    st.caption("Run pipeline steps. Inputs above each button; each button runs the corresponding CLI command.")
    today = date.today()

    # --- Finding/Isolating Jobs ---
    st.subheader("Finding/Isolating Jobs")

    _pipe_button("Pop Jobs", SCRIPTS_DIR / "populate_jobs.py", [], None, desc="Populate jobs from the sheet.")

    _pipe_button("Archive Jobs", SCRIPTS_DIR / "batch_archive_from_sheet.py", [], None, desc="Archive jobs in bulk from the sheet.")

    st.divider()
    company_fit = st.text_input("Company filter for **Batch Fit Score** (leave blank for all)", key="pipe_batch_fit_company", placeholder="e.g. Costco")
    script_fit = SCRIPTS_DIR / "batch_initial_fit_score_agent.py"
    if company_fit and company_fit.strip():
        _pipe_button("Batch Fit Score", script_fit, [company_fit.strip()], None, desc="Run initial fit scoring (company filter).")
    else:
        overwrite_fit = st.radio("New only / Overwrite all", ["New only", "Overwrite all"], key="pipe_batch_fit_overwrite", horizontal=True)
        stdin_fit = "A\n" if overwrite_fit == "Overwrite all" else "N\n"
        c1, c2 = st.columns([1, 8])
        with c1:
            batch_fit_clicked = st.button("Batch Fit Score", key="pipe_batch_fit_btn")
        with c2:
            st.caption("Run initial fit scoring for all (new only or overwrite).")
        if batch_fit_clicked:
            if script_fit.exists():
                st.info("This may take several minutes depending on the number of rows.")
                with st.spinner("Running Batch Fit Score…"):
                    code, out, err = run_cmd(script_fit, [], stdin_fit)
                if code != 0:
                    st.error(f"**Batch Fit Score** failed (exit code {code})")
                    if err:
                        st.code(err, language="text")
                    if out:
                        st.code(out, language="text")
                else:
                    st.success("**Batch Fit Score** completed.")
                    combined = (out.strip() + "\n\n" + err.strip()).strip()
                    if combined:
                        st.code(combined, language="text")
            else:
                st.error(f"Script not found: {script_fit}")

    st.divider()
    st.warning("⚠️ If this is the first time running a company through Batch Metadata, run it in the terminal instead. The UI can't respond to the LinkedIn company picker prompt.")
    company_meta = st.text_input("Company filter for **Batch Metadata** (leave blank for all)", key="pipe_batch_metadata_company", placeholder="e.g. Costco")
    script_meta = SCRIPTS_DIR / "batch_extract_metadata.py"
    if company_meta and company_meta.strip():
        _pipe_button("Batch Metadata", script_meta, [company_meta.strip()], None, desc="Extract metadata (company filter).")
    else:
        overwrite_meta = st.radio("New only / Overwrite all", ["New only", "Overwrite all"], key="pipe_batch_metadata_overwrite", horizontal=True)
        stdin_meta = "A\n" if overwrite_meta == "Overwrite all" else "N\n"
        c1, c2 = st.columns([1, 8])
        with c1:
            batch_meta_clicked = st.button("Batch Metadata", key="pipe_batch_metadata_btn")
        with c2:
            st.caption("Extract metadata for all (new only or overwrite).")
        if batch_meta_clicked:
            if script_meta.exists():
                st.info("This may take several minutes depending on the number of rows.")
                with st.spinner("Running Batch Metadata…"):
                    code, out, err = run_cmd(script_meta, [], stdin_meta)
                if code != 0:
                    st.error(f"**Batch Metadata** failed (exit code {code})")
                    if err:
                        st.code(err, language="text")
                    if out:
                        st.code(out, language="text")
                else:
                    st.success("**Batch Metadata** completed.")
                    combined = (out.strip() + "\n\n" + err.strip()).strip()
                    if combined:
                        st.code(combined, language="text")
            else:
                st.error(f"Script not found: {script_meta}")

    # --- Applying ---
    st.subheader("Applying")

    st.divider()
    d_dup_resume = st.date_input("Date (Dup Resume)", value=today, key="pipe_dup_resume_date")
    _pipe_button("Dup Resume", SCRIPTS_DIR / "duplicate_resume_docs.py", [d_dup_resume.strftime("%Y-%m-%d")], None, desc="Duplicate resume docs for the selected date.")

    st.divider()
    d_dup_cl = st.date_input("Date (Dup Cover Letter)", value=today, key="pipe_dup_cl_date")
    _pipe_button("Dup Cover Letter", SCRIPTS_DIR / "duplicate_cover_letter_docs.py", [d_dup_cl.strftime("%Y-%m-%d")], None, desc="Duplicate cover letter docs for the selected date.")

    st.divider()
    d_bullets = st.date_input("Date (Generate Bullets)", value=today, key="pipe_gen_bullets_date")
    _pipe_button("Generate Bullets", SCRIPTS_DIR / "batch_generate_bullets_agent.py", [d_bullets.strftime("%Y-%m-%d")], None, desc="Generate resume bullets for the selected date.")

    st.divider()
    d_evalskills = st.date_input("Date (Eval Skills)", value=today, key="pipe_eval_skills_date")
    _pipe_button("Eval Skills", SCRIPTS_DIR / "evaluate_resume_skills_agent.py", [d_evalskills.strftime("%Y-%m-%d")], None, desc="Evaluate resume skills fit for the selected date.")

    st.divider()
    d_evalintro = st.date_input("Date (Eval Intro/Edu)", value=today, key="pipe_eval_intro_date")
    _pipe_button("Eval Intro/Edu", SCRIPTS_DIR / "evaluate_intro_education_agent.py", [d_evalintro.strftime("%Y-%m-%d")], None, desc="Evaluate intro and education for the selected date.")

    st.divider()
    d_gencl = st.date_input("Date (Generate Cover Letters)", value=today, key="pipe_gen_cl_date")
    _pipe_button("Generate Cover Letters", SCRIPTS_DIR / "batch_generate_cover_letter_agent.py", [d_gencl.strftime("%Y-%m-%d")], None, desc="Generate cover letters for the selected date.")

    st.divider()
    d_hm = st.date_input("Date (Generate HM Outreach)", value=today, key="pipe_hm_date")
    _pipe_button("Generate HM Outreach", SCRIPTS_DIR / "batch_generate_hm_outreach_agent.py", [d_hm.strftime("%Y-%m-%d")], None, desc="Generate hiring manager outreach for the selected date.")

    # --- Maintenance ---
    st.subheader("Maintenance")
    st.divider()
    dry_run = st.checkbox("Preview only (don't delete)", key="pipe_cleanup_dry_run", help="Show what would be removed without deleting. Uncheck to actually remove orphan folders.")
    args_cleanup = ["--dry-run"] if dry_run else []
    c1, c2 = st.columns([1, 8])
    with c1:
        cleanup_clicked = st.button("Cleanup", key="pipe_cleanup_btn")
    with c2:
        st.caption("Remove orphan job folders (use Preview only to see changes without deleting).")
    if cleanup_clicked:
        script_cleanup = SCRIPTS_DIR / "cleanup_orphan_job_folders.py"
        if script_cleanup.exists():
            st.info("This may take several minutes depending on the number of rows.")
            with st.spinner("Running Cleanup…"):
                code, out, err = run_cmd(script_cleanup, args_cleanup, None)
            if code != 0:
                st.error(f"**Cleanup** failed (exit code {code})")
                if err:
                    st.code(err, language="text")
                if out:
                    st.code(out, language="text")
            else:
                st.success("**Cleanup** completed.")
                combined = (out.strip() + "\n\n" + err.strip()).strip()
                if combined:
                    st.code(combined, language="text")
        else:
            st.error(f"Script not found: {script_cleanup}")


def page_analytics():
    st.header("Analytics")
    st.caption("Funnel stats and follow-up identification.")
    script_funnel = SCRIPTS_DIR / "funnel_stats.py"
    if script_funnel.exists():
        c1, c2 = st.columns([1, 8])
        with c1:
            funnel_clicked = st.button("Funnel Stats", key="ana_funnel")
        with c2:
            st.caption("Show funnel stats (applied → interviews → offers).")
        if funnel_clicked:
            st.info("This may take several minutes depending on the number of rows.")
            with st.spinner("Running Funnel Stats…"):
                code, out, err = run_cmd(script_funnel, [], None)
            if code != 0:
                st.error("**Funnel Stats** failed (exit code {})".format(code))
                if err:
                    st.code(err, language="text")
                if out:
                    st.code(out, language="text")
            else:
                st.success("**Funnel Stats** completed.")
                combined = (out.strip() + "\n\n" + err.strip()).strip()
                if combined:
                    st.code(combined, language="text")
    else:
        st.error(f"Script not found: {script_funnel}")

    n_followups = st.number_input("N (days since applied)", min_value=1, value=10, key="ana_followups_n")
    script_followups = SCRIPTS_DIR / "identify_followups.py"
    c1, c2 = st.columns([1, 8])
    with c1:
        followups_clicked = st.button("Identify Follow-ups", key="ana_followups")
    with c2:
        st.caption("List applications needing follow-up (N+ days since applied).")
    if followups_clicked:
        if script_followups.exists():
            st.info("This may take several minutes depending on the number of rows.")
            with st.spinner("Running Identify Follow-ups…"):
                code, out, err = run_cmd(script_followups, [str(int(n_followups))], None)
            if code != 0:
                st.error("**Identify Follow-ups** failed (exit code {})".format(code))
                if err:
                    st.code(err, language="text")
                if out:
                    st.code(out, language="text")
            else:
                st.success("**Identify Follow-ups** completed.")
                combined = (out.strip() + "\n\n" + err.strip()).strip()
                if combined:
                    st.code(combined, language="text")
        else:
            st.error(f"Script not found: {script_followups}")


def main():
    st.set_page_config(page_title="RoleSynth", layout="wide", initial_sidebar_state="expanded")
    st.sidebar.title("RoleSynth")
    st.sidebar.caption("Job search automation")
    page = st.sidebar.radio(
        "Section",
        ["Pipeline", "Analytics"],
        label_visibility="collapsed",
    )
    if page == "Pipeline":
        page_pipeline()
    else:
        page_analytics()


if __name__ == "__main__":
    main()
