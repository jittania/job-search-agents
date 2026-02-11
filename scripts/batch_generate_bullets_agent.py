"""Batch: generate resume_bullets.json for all job folders for a given day (default today). Skips folders that already have resume_bullets.json."""
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BULLETS_SCRIPT = SCRIPT_DIR / "generate_bullets_agent.py"
DATA_DIR = Path("data")
OUTPUT_FILE = "resume_bullets.json"


def is_job_dir_path(arg: str) -> bool:
    p = Path(arg).resolve()
    return p.is_dir() and (p / "job.txt").exists()


def iter_job_dirs_for_day(data_dir: Path, day: str):
    for company_dir in data_dir.iterdir():
        if not company_dir.is_dir():
            continue
        day_dir = company_dir / day
        if day_dir.is_dir():
            yield day_dir


def main():
    # Single job path: genbullets data/costco/2026-02-10 → overwrites if present
    if len(sys.argv) == 2 and is_job_dir_path(sys.argv[1]):
        job_dir = Path(sys.argv[1]).resolve()
        print(f"📋 Bullets (single): {job_dir}")
        subprocess.run(["python", str(BULLETS_SCRIPT), str(job_dir)], check=True)
        return

    day = date.today().isoformat()
    if len(sys.argv) == 2:
        arg = sys.argv[1].strip().lower()
        if arg == "today":
            day = date.today().isoformat()
        else:
            day = arg  # expect YYYY-MM-DD

    if not DATA_DIR.exists():
        raise SystemExit("Missing data/ directory.")

    wrote = 0
    skipped = 0

    for job_dir in iter_job_dirs_for_day(DATA_DIR, day):
        job_txt = job_dir / "job.txt"
        out_path = job_dir / OUTPUT_FILE

        if not job_txt.exists():
            skipped += 1
            continue
        if out_path.exists():
            skipped += 1
            continue

        print(f"📋 Bullets: {job_dir.relative_to(DATA_DIR)}")
        subprocess.run(
            ["python", str(BULLETS_SCRIPT), str(job_dir)],
            check=True,
        )
        wrote += 1

    print(f"\n✅ Done. wrote={wrote} skipped={skipped}\n")


if __name__ == "__main__":
    main()
