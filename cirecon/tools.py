import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import requests
from github import Github

from cirecon.rule_engine import run_all_checks
from cirecon.validator import validate_schema


@dataclass
class ToolResult:
    success: bool
    data: dict
    error: Optional[str] = None


def read_workflow_file(path: str) -> ToolResult:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(success=True, data={"path": path, "content": content})
    except Exception as e:
        return ToolResult(success=False, data={}, error=str(e))


def validate_yaml_schema_tool(content: str) -> ToolResult:
    result = validate_schema(content)
    return ToolResult(
        success=result.passed,
        data={"passed": result.passed},
        error="; ".join(result.errors) if result.errors else None,
    )


def run_rule_checks_tool(path: str, content: str) -> ToolResult:
    issues = run_all_checks(path, content)
    issues_data = [
        {
            "id": i.id,
            "severity": i.severity.value,
            "message": i.message,
            "location": {
                "file": i.location.file,
                "line": i.location.line,
                "column": i.location.column,
            },
            "auto_fixable": i.auto_fixable,
            "confidence": i.confidence,
            "suggested_fix": i.suggested_fix,
        }
        for i in issues
    ]
    return ToolResult(success=True, data={"issues": issues_data, "count": len(issues_data)})


def check_secret_exists(secret_name: str, github_token: str, repo: str) -> ToolResult:
    url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return ToolResult(success=True, data={"exists": True})
        if resp.status_code == 404:
            return ToolResult(success=True, data={"exists": False})
        resp.raise_for_status()
        return ToolResult(success=True, data={"exists": False})
    except requests.RequestException as e:
        return ToolResult(success=False, data={}, error=str(e))


CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def propose_fix(issue_dict: dict, file_section: str, api_key: str) -> ToolResult:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2000,
        "system": (
            "You are a GitHub Actions YAML repair tool. "
            "Return only the fixed YAML block, nothing else."
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Issue: {issue_dict.get('message', '')}\n\n"
                    f"File section:\n```yaml\n{file_section}\n```\n\n"
                    "Fix the YAML above."
                ),
            }
        ],
    }
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        patch = data["content"][0]["text"]
        return ToolResult(
            success=True,
            data={"patch": patch.strip(), "confidence": 0.85},
        )
    except requests.RequestException as e:
        return ToolResult(success=False, data={}, error=str(e))
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return ToolResult(success=False, data={}, error=f"Parse error: {e}")


def apply_fix_tool(path: str, patch: str) -> ToolResult:
    try:
        return ToolResult(
            success=True,
            data={"path": path, "patched": patch},
        )
    except Exception as e:
        return ToolResult(success=False, data={}, error=str(e))


def create_branch_and_pr(
    patches: list,
    issues_fixed: list,
    unresolved: list,
    github_token: str,
    repo: str,
) -> ToolResult:
    try:
        branch_name = f"ci-recon/fix-{int(time.time())}"

        subprocess.run(
            ["git", "config", "--global", "safe.directory", "*"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "cirecon@ci-recon.dev"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "CIRecon"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-B", branch_name],
            check=True, capture_output=True,
        )

        for patch in patches:
            if not patch['path'].startswith('.github/workflows/'):
                raise ValueError(f"CIRecon attempted to patch non-workflow file: {patch['path']}")

        workflow_patches = [p for p in patches if p['path'].startswith('.github/workflows/')]

        print(f"DEBUG: Files to commit: {[p['path'] for p in workflow_patches]}")
        for patch in workflow_patches:
            debug_msg = (
                f"DEBUG: {patch['path']} — {len(patch['content'])} bytes "
                f"— has jobs: {'jobs:' in patch['content']}"
            )
            print(debug_msg)

        for patch in workflow_patches:
            file_path = patch["path"]
            content = patch["content"]
            print(f"DEBUG: Writing {file_path} ({len(content)} bytes)")
            print(f"DEBUG: First 200 chars: {content[:200]}")
            print(f"DEBUG: Last 200 chars: {content[-200:]}")
            print(f"DEBUG: Contains 'jobs:': {'jobs:' in content}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        print("DEBUG: Running git add .github/workflows/")

        subprocess.run(["git", "add", ".github/workflows/"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "[CIRecon] Auto-fix CI/CD workflow issues"],
            check=True, capture_output=True,
        )
        remote_url = f"https://x-access-token:{github_token}@github.com/{repo}.git"
        subprocess.run(["git", "push", remote_url, branch_name], check=True, capture_output=True)

        fixed_rows = "\n".join(
            f"| `{i['id']}` | {i.get('message', '')} | Fixed |"
            for i in issues_fixed
        )
        unresolved_rows = "\n".join(
            f"| `{i['id']}` | {i.get('message', '')} | Unresolved |"
            for i in unresolved
        )
        body = f"""## CIRecon Automated Fix

### Fixed Issues
| Issue ID | Description | Status |
|---|---|---|
{fixed_rows}

### Unresolved Issues
| Issue ID | Description | Status |
|---|---|---|
{unresolved_rows if unresolved_rows else 'None — all issues resolved.'}
"""

        g = Github(github_token)
        repo_obj = g.get_repo(repo)
        default_branch = repo_obj.default_branch
        title = "CIRecon: Automated workflow repairs"
        pr = repo_obj.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=default_branch,
        )
        return ToolResult(success=True, data={"pr_url": pr.html_url})
    except Exception as e:
        return ToolResult(success=False, data={}, error=str(e))
