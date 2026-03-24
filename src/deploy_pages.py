"""Deploy latest reports to GitHub Pages."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "gh-pages"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"
REPO_URL = "https://github.com/pottsmt/dat-dashboard.git"


def _force_remove(path: Path):
    """Remove directory, handling Windows .git file locks."""
    import stat
    def on_error(func, fpath, exc_info):
        Path(fpath).chmod(stat.S_IWRITE)
        func(fpath)
    shutil.rmtree(path, onexc=on_error)


def deploy():
    """Copy latest report + company pages to gh-pages and push."""
    # Find the latest report
    reports = sorted(REPORTS_DIR.glob("dat_report_*.html"), reverse=True)
    if not reports:
        logger.warning("No reports found to deploy")
        return False

    latest = reports[0]
    logger.info("Deploying %s to GitHub Pages", latest.name)

    # Set up gh-pages working directory
    if PAGES_DIR.exists():
        _force_remove(PAGES_DIR)

    # Clone just the gh-pages branch (shallow)
    result = subprocess.run(
        ["git", "clone", "--branch", "gh-pages", "--depth", "1", REPO_URL, str(PAGES_DIR)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("Failed to clone gh-pages: %s", result.stderr)
        return False

    # Copy latest report as index.html
    shutil.copy2(latest, PAGES_DIR / "index.html")

    # Copy company detail pages
    companies_src = REPORTS_DIR / "companies"
    companies_dst = PAGES_DIR / "companies"
    if companies_src.exists():
        if companies_dst.exists():
            shutil.rmtree(companies_dst)
        shutil.copytree(companies_src, companies_dst)

        # Fix back-links in company pages to point to root
        for html_file in companies_dst.glob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            # Replace "../dat_report_YYYY-MM-DD.html" with "../"
            import re
            content = re.sub(r'href="\.\./dat_report_[^"]*\.html"', 'href="../"', content)
            html_file.write_text(content, encoding="utf-8")

    # Commit and push
    env = {"GIT_DIR": str(PAGES_DIR / ".git"), "GIT_WORK_TREE": str(PAGES_DIR)}
    subprocess.run(["git", "add", "-A"], cwd=str(PAGES_DIR), capture_output=True)

    # Check if there are changes
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(PAGES_DIR),
        capture_output=True, text=True,
    )
    if not status.stdout.strip():
        logger.info("No changes to deploy")
        return True

    date_str = latest.stem.replace("dat_report_", "")
    subprocess.run(
        ["git", "commit", "-m", f"Update dashboard - {date_str}"],
        cwd=str(PAGES_DIR), capture_output=True, text=True,
    )

    push = subprocess.run(
        ["git", "push"], cwd=str(PAGES_DIR),
        capture_output=True, text=True,
    )
    if push.returncode != 0:
        logger.error("Failed to push: %s", push.stderr)
        return False

    logger.info("Deployed to https://pottsmt.github.io/dat-dashboard/")

    # Clean up
    _force_remove(PAGES_DIR)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deploy()
