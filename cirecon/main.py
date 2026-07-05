import os
import sys

from cirecon.agent_loop import run_agent_loop
from cirecon.fix_applier import apply_fix
from cirecon.input_layer import discover_workflow_files
from cirecon.memory import (
    FixRecord,
    MemoryContext,
    load_memory,
    record_fix,
    save_memory,
)
from cirecon.rule_engine import Issue, run_all_checks
from cirecon.tools import create_branch_and_pr
from cirecon.validator import validate_all


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


def run():
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    github_token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    max_iterations = int(os.getenv("MAX_ITERATIONS", "10"))
    fail_on_unresolved = os.getenv("FAIL_ON_UNRESOLVED", "false").lower() == "true"

    github_workspace = os.getenv("GITHUB_WORKSPACE")
    is_docker = os.path.exists("/github/workspace")
    workspace = github_workspace or ("/github/workspace" if is_docker else ".")

    memory = load_memory(workspace)

    files = discover_workflow_files(workspace)
    if not files:
        print("No workflow files found.")
        sys.exit(0)

    all_issues: list[Issue] = []
    file_contents: dict[str, str] = {}
    for path, content in files:
        file_contents[path] = content
        issues = run_all_checks(path, content)
        all_issues.extend(issues)
        for issue in issues:
            print(f"  [{issue.severity.value.upper()}] {issue.id}: {issue.message}")

    if not all_issues:
        print("No issues found — all workflows are clean.")
        sys.exit(0)

    patches: list[dict] = []
    issues_fixed: list[dict] = []
    unresolved_dicts: list[dict] = []

    for issue in all_issues:
        d = _issue_to_dict(issue)
        if not issue.auto_fixable:
            unresolved_dicts.append(d)
            continue

        path = issue.location.file
        content = file_contents.get(path, "")
        if not content:
            unresolved_dicts.append(d)
            continue

        new_content = apply_fix(content, issue)
        validation = validate_all(path, new_content, [issue])
        if validation.passed:
            patches.append({"path": path, "content": new_content})
            file_contents[path] = new_content
            issues_fixed.append(d)
            print(f"  FIXED: {issue.id} in {path}")
        else:
            unresolved_dicts.append(d)
            print(f"  FAILED: {issue.id} in {path} — fix did not pass validation")

    if unresolved_dicts and anthropic_api_key:
        print(f"\nRunning agent loop for {len(unresolved_dicts)} unresolved issues...")
        state = run_agent_loop(
            unresolved=unresolved_dicts,
            memory=memory,
            api_key=anthropic_api_key,
            max_iterations=max_iterations,
            repo=repo,
            github_token=github_token,
        )
        for p in state.patches:
            if p not in patches:
                patches.append(p)
        for fix in state.issues_fixed:
            if fix not in issues_fixed:
                issues_fixed.append(fix)
        unresolved_dicts = state.unresolved
        print(f"  Agent loop completed: {len(issues_fixed)} fixed, {len(unresolved_dicts)} unresolved")

    if patches and github_token and repo:
        result = create_branch_and_pr(
            patches=patches,
            issues_fixed=issues_fixed,
            unresolved=unresolved_dicts,
            github_token=github_token,
            repo=repo,
        )
        if result.success:
            pr_url = result.data.get("pr_url", "")
            print(f"Pull request created: {pr_url}")
            for fix in issues_fixed:
                record = FixRecord(
                    issue_id=fix["id"],
                    file=fix.get("location", {}).get("file", ""),
                    fix_applied=fix.get("message", ""),
                    pr_url=pr_url,
                    pr_status="open",
                )
                record_fix(memory, record)
        else:
            print(f"Failed to create PR: {result.error}", file=sys.stderr)

    memory.total_runs += 1
    save_memory(memory, workspace)

    if unresolved_dicts and fail_on_unresolved:
        print(f"\n{len(unresolved_dicts)} issue(s) remain unresolved. Failing.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    run()
