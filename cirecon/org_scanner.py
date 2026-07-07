import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

from cirecon.input_layer import discover_workflow_files
from cirecon.rule_engine import Issue, run_all_checks


def strip_tmpdir(path: str, tmpdir: str) -> str:
    if path.startswith(tmpdir):
        return path[len(tmpdir):].lstrip(os.sep)
    return path


@dataclass
class RepoReport:
    repo: str
    files_scanned: int
    issues: list[Issue]
    health_score: int
    scanned_at: str


def _calculate_health_score(issues: list[Issue]) -> int:
    score = 100
    for issue in issues:
        sev = issue.severity.value
        if sev == "critical":
            score -= 20
        elif sev == "high":
            score -= 10
        elif sev == "medium":
            score -= 5
        elif sev == "low":
            score -= 2
    return max(score, 0)


def scan_repos(repo_list: list[str], github_token: str) -> list[RepoReport]:
    reports: list[RepoReport] = []

    for repo in repo_list:
        repo = repo.strip()
        if not repo:
            continue

        tmpdir = tempfile.mkdtemp()
        try:
            remote_url = f"https://x-access-token:{github_token}@github.com/{repo}.git"
            subprocess.run(
                ["git", "clone", "--depth", "1", remote_url, tmpdir],
                check=True, capture_output=True, timeout=120,
            )

            files = discover_workflow_files(tmpdir)
            all_issues: list[Issue] = []
            for path, content in files:
                issues = run_all_checks(path, content)
                for issue in issues:
                    issue.location.file = strip_tmpdir(issue.location.file, tmpdir)
                all_issues.extend(issues)

            score = _calculate_health_score(all_issues)
            print(f"DEBUG: {repo} — {len(all_issues)} issues found, health score: {score}")
            report = RepoReport(
                repo=repo,
                files_scanned=len(files),
                issues=all_issues,
                health_score=score,
                scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            )
            reports.append(report)
        except subprocess.TimeoutExpired:
            reports.append(RepoReport(
                repo=repo, files_scanned=0, issues=[],
                health_score=0,
                scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            ))
        except Exception:
            reports.append(RepoReport(
                repo=repo, files_scanned=0, issues=[],
                health_score=0,
                scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            ))
        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

    return reports
