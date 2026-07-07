from datetime import datetime, timezone

import requests

from cirecon.org_scanner import RepoReport


def generate_dashboard_markdown(reports: list[RepoReport]) -> str:
    if not reports:
        return "# CIRecon Org Health Dashboard\n\nNo repos scanned.\n"

    total_critical = sum(
        1 for r in reports for i in r.issues if i.severity.value == "critical"
    )
    total_high = sum(
        1 for r in reports for i in r.issues if i.severity.value == "high"
    )
    avg_score = sum(r.health_score for r in reports) // len(reports)
    clean_count = sum(1 for r in reports if not r.issues)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# CIRecon Org Health Dashboard",
        f"Last updated: {now}",
        "",
        "## Summary",
        "| Metric | Value |",
        "|---|---|",
        f"| Repos scanned | {len(reports)} |",
        f"| Average health score | {avg_score}/100 |",
        f"| Critical issues | {total_critical} |",
        f"| High issues | {total_high} |",
        f"| Clean repos | {clean_count} |",
        "",
        "## Repo Health Scores",
        "| Repo | Health Score | Issues | Status |",
        "|---|---|---|---|",
    ]

    for r in reports:
        if r.health_score == 100:
            status = "✅ Clean"
        elif r.health_score >= 70:
            status = "🟡 Minor issues"
        else:
            status = "⚠️ Issues found"
        lines.append(
            f"| {r.repo} | {r.health_score}/100 | {len(r.issues)} | {status} |"
        )

    lines.append("")
    lines.append("## Issues by Repo")

    for r in reports:
        if not r.issues:
            continue
        lines.append(f"### {r.repo}")
        lines.append("| File | Rule | Severity | Fix |")
        lines.append("|---|---|---|---|")
        for issue in r.issues:
            fix = f"`{issue.suggested_fix}`" if issue.suggested_fix else "Manual fix required"
            lines.append(
                f"| `{issue.location.file}` | `{issue.id}` | "
                f"{issue.severity.value.upper()} | {fix} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def publish_to_gist(markdown: str, github_token: str, gist_id: str = None) -> str:
    token = github_token.strip()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    gist_data = {
        "description": "CIRecon Org Health Dashboard",
        "public": False,
        "files": {
            "cirecon-dashboard.md": {
                "content": markdown,
            }
        },
    }

    if gist_id:
        print(f"DEBUG: Attempting to update gist {gist_id}")
        resp = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers=headers,
            json=gist_data,
            timeout=30,
        )
    else:
        print("DEBUG: Creating new gist")
        resp = requests.post(
            "https://api.github.com/gists",
            headers=headers,
            json=gist_data,
            timeout=30,
        )

    print(f"DEBUG: Response status: {resp.status_code}")
    print(f"DEBUG: Response body: {resp.text[:200]}")

    if not resp.ok:
        print(f"Gist API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    url = resp.json()["html_url"]
    print(f"Gist published: {url}")
    return url
