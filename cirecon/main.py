import os
import sys

from cirecon.dashboard import generate_dashboard_markdown, publish_to_gist
from cirecon.fix_applier import apply_fix
from cirecon.input_layer import discover_workflow_files
from cirecon.memory import load_memory, record_detection, save_memory
from cirecon.org_scanner import scan_repos
from cirecon.rule_engine import Issue, run_all_checks
from cirecon.validator import validate_all

MEMORY_DIR = os.path.join(os.getenv("GITHUB_WORKSPACE", "."), ".cirecon-memory")
MEMORY_PATH = os.path.join(MEMORY_DIR, "memory.json")


def _issue_to_dict(issue: Issue) -> dict:
    return {
        "id": issue.id,
        "severity": issue.severity.value,
        "message": issue.message,
        "location": {
            "file": issue.location.file,
            "line": issue.location.line,
            "column": issue.location.column,
        },
        "auto_fixable": issue.auto_fixable,
        "confidence": issue.confidence,
        "suggested_fix": issue.suggested_fix,
    }


def write_job_summary(
    files_scanned: list,
    issues_found: list[Issue],
    issues_fixed: list[dict],
    unresolved: list[dict],
) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("## CIRecon Report\n\n")
        f.write(f"**Files scanned:** {len(files_scanned)} | ")
        f.write(f"**Issues found:** {len(issues_found)} | ")
        f.write(f"**Auto-fixable:** {len(issues_fixed)} | ")
        f.write(f"**Needs attention:** {len(unresolved)}\n\n")

        if issues_found:
            f.write("### Issues Found\n\n")
            f.write("| File | Rule | Severity | Auto-fixable | Suggested Fix |\n")
            f.write("|---|---|---|---|---|\n")
            for issue in issues_found:
                fixable = '✅' if issue.auto_fixable else '❌'
                fix = f'`{issue.suggested_fix}`' if issue.suggested_fix else 'Manual fix required'
                f.write(f"| `{issue.location.file}` | `{issue.id}` | "
                        f"{issue.severity.value.upper()} | {fixable} | {fix} |\n")
        else:
            f.write("### ✅ All workflows are clean\n\n")
            f.write("No issues detected in any workflow file.\n")


def run() -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    print(f"Memory directory created: {MEMORY_DIR}")

    memory = load_memory(MEMORY_PATH)
    print(f"Memory loaded: {memory.total_runs} previous runs")

    fail_on_unresolved = os.getenv("FAIL_ON_UNRESOLVED", "false").lower() == "true"

    print(f"Working directory: {os.getcwd()}")
    print(f"Files in current dir: {os.listdir('.')}")
    repo_path = "."

    files = discover_workflow_files(repo_path)
    if not files:
        print("No workflow files found.")
        memory.total_runs += 1
        save_memory(memory, MEMORY_PATH)
        print(f"Memory saved: {memory.total_runs} total runs, {len(memory.fixes)} issues tracked")
        sys.exit(0)

    all_issues: list[Issue] = []
    file_contents: dict[str, str] = {}
    file_issues: dict[str, list[Issue]] = {}
    for path, content in files:
        file_contents[path] = content
        issues = run_all_checks(path, content)
        file_issues[path] = issues
        all_issues.extend(issues)
        for issue in issues:
            print(f"  [{issue.severity.value.upper()}] {issue.id}: {issue.message}")

    # inline GitHub Actions annotations
    for issue in all_issues:
        level = "error" if issue.severity.value in ["critical", "high"] else "warning"
        line = issue.location.line or 1
        print(f"::{level} file={issue.location.file},line={line},title={issue.id}::{issue.message}")

    memory.total_runs += 1
    for issue in all_issues:
        memory = record_detection(memory, issue)

    if not all_issues:
        print("No issues found — all workflows are clean.")
        write_job_summary(files, [], [], [])
        save_memory(memory, MEMORY_PATH)
        print(f"Memory saved: {memory.total_runs} total runs, {len(memory.fixes)} issues tracked")
        sys.exit(0)

    issues_fixed: list[dict] = []
    unresolved_dicts: list[dict] = []

    # group issues by file for sequential accumulation
    file_issues_list: dict[str, list[tuple[Issue, dict]]] = {}
    for issue in all_issues:
        d = _issue_to_dict(issue)
        path = issue.location.file
        if path not in file_issues_list:
            file_issues_list[path] = []
        file_issues_list[path].append((issue, d))

    for path, issue_pairs in file_issues_list.items():
        current_content = file_contents.get(path, "")
        if not current_content:
            for issue, d in issue_pairs:
                unresolved_dicts.append(d)
            continue

        for issue, d in issue_pairs:
            if not issue.auto_fixable:
                unresolved_dicts.append(d)
                continue

            new_content = apply_fix(current_content, issue)
            validation = validate_all(path, new_content, file_issues.get(path, [issue]))
            if validation.passed:
                current_content = new_content
                issues_fixed.append(d)
                print(f"  FIXED: {issue.id} in {path}")
            else:
                unresolved_dicts.append(d)
                print(f"  FAILED: {issue.id} in {path} — {' | '.join(validation.errors)}")

    save_memory(memory, MEMORY_PATH)
    print(f"Memory saved: {memory.total_runs} total runs, {len(memory.fixes)} issues tracked")

    if unresolved_dicts and fail_on_unresolved:
        write_job_summary(files, all_issues, issues_fixed, unresolved_dicts)
        print(f"\n{len(unresolved_dicts)} issue(s) remain unresolved. Failing.")
        sys.exit(1)

    write_job_summary(files, all_issues, issues_fixed, unresolved_dicts)
    sys.exit(0)


def run_dashboard() -> None:
    github_token = (
        os.getenv("CIRECON_GITHUB_TOKEN") or
        os.getenv("GITHUB_TOKEN") or
        ""
    ).strip()
    repos_str = os.getenv("REPOS", "")
    gist_id = os.getenv("GIST_ID", "")

    if not github_token:
        print("CIRECON_GITHUB_TOKEN (or GITHUB_TOKEN) is required for dashboard mode.")
        sys.exit(1)
    if not repos_str:
        print("REPOS env var is required for dashboard mode (comma-separated).")
        sys.exit(1)

    repo_list = [r.strip() for r in repos_str.split(",") if r.strip()]
    print(f"Scanning {len(repo_list)} repos...")

    reports = scan_repos(repo_list, github_token)

    markdown = generate_dashboard_markdown(reports)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown)

    try:
        gist_url = publish_to_gist(markdown, github_token, gist_id or None)
        print(f"Dashboard published: {gist_url}")
    except Exception as e:
        print(f"Failed to publish gist: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    mode = os.getenv("MODE", "scan")
    if mode == "dashboard":
        run_dashboard()
    else:
        run()
