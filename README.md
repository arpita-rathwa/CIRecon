# CIRecon

> A GitHub Code Scanning provider for CI/CD workflows — detects security misconfigurations and correctness issues in GitHub Actions, with findings that appear permanently in your Security tab.

[![CI](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml/badge.svg)](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/GitHub-Marketplace-orange)](https://github.com/marketplace/actions/cirecon)
[![Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)](https://github.com/arpita-rathwa/CIRecon)

---

## What it does

CIRecon scans your GitHub Actions workflow files on every push and pull request. It checks for security misconfigurations, correctness issues, and runtime behavioral gaps that only surface when your workflow behaves differently between events.

Findings appear in three places:

- **Security → Code Scanning tab** — permanently, with history, dismissals, and PR integration — just like CodeQL
- **Inline annotations** — red and yellow markers on the exact file and line in your Actions UI
- **Job Summary** — a structured report on every Actions run page

CIRecon also remembers what it has already told you. After flagging an issue, it stays quiet about it on subsequent runs — no repeated noise for things you already know about. Issues that keep recurring get escalated to higher severity automatically.

---

## Quickstart

```yaml
name: CIRecon

on:
  push:
    paths:
      - '.github/workflows/**'
  pull_request:
    paths:
      - '.github/workflows/**'

jobs:
  cirecon:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        with:
          path: .cirecon-memory
          key: cirecon-memory-${{ github.repository }}
      - uses: arpita-rathwa/CIRecon@v1
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: cirecon-results.sarif
          category: cirecon
```

`actions/cache` enables memory — CIRecon remembers what it has flagged across runs. `upload-sarif` sends findings to GitHub's Code Scanning tab. Both are optional — CIRecon still produces inline annotations and a Job Summary without them.

> **Note:** SARIF upload requires `permissions: security-events: write` and works on public repos or repos with GitHub Advanced Security enabled.

See [`examples/cirecon.yml`](examples/cirecon.yml) for the full configuration.

---

## What CIRecon checks

### Correctness

| Rule | What it catches | Severity |
|---|---|---|
| `RULE_DEPRECATED_ACTION` | Actions pinned to outdated versions like `checkout@v2`. SHA-pinned actions are exempt. | MEDIUM |
| `RULE_MISSING_PERMISSIONS_BLOCK` | No top-level `permissions:` block — `GITHUB_TOKEN` gets broad default access. | HIGH |
| `RULE_BROKEN_NEEDS_DEPENDENCY` | A `needs:` entry referencing a job ID that does not exist — a silent pipeline ordering bug. | HIGH |

### Security

| Rule | What it catches | Severity |
|---|---|---|
| `RULE_SECRET_IN_RUN_COMMAND` | `${{ secrets.* }}` inside a `run:` step — secret values appear in plain text in your logs. | CRITICAL |
| `RULE_PULL_REQUEST_TARGET_UNSAFE` | `pull_request_target` combined with checkout of the PR ref — a known RCE vector that gives untrusted code write access to your repo. | CRITICAL |
| `RULE_OVERLY_BROAD_PERMISSIONS` | `write-all` or three or more write-level permission scopes — increases blast radius if the workflow is compromised. | HIGH |
| `RULE_UNPINNED_THIRD_PARTY_ACTION` | A third-party action not pinned to a full commit SHA — can be silently updated with malicious code. | HIGH |

### Runtime behavioral

These are the issues that don't show up in syntax checkers. They only surface when your workflow behaves differently between events.

| Rule | What it catches | Severity |
|---|---|---|
| `RULE_FORK_PR_SECRET_EXPOSURE` | A `pull_request` workflow that uses secrets — secrets are unavailable on fork PRs and silently become empty strings. | HIGH |
| `RULE_WRITE_STEP_ON_FORK_TRIGGER` | A step requiring write permissions in a `pull_request` workflow — silently fails on fork PRs which use a read-only token. | HIGH |
| `RULE_REF_CONDITION_MISMATCH` | `if: github.ref == 'refs/heads/...'` in a workflow triggered by both `push` and `pull_request` — always false on PRs, step silently skips. | MEDIUM |

---

## Output

### GitHub Code Scanning (SARIF)

CIRecon writes findings to `cirecon-results.sarif` in standard SARIF 2.1.0 format. When uploaded via `github/codeql-action/upload-sarif`, findings appear in **Security → Code Scanning** with:

- Permanent history across runs
- Developer-controlled dismissals with reasons
- PR checks that block merge when new issues are introduced
- Org-wide Security Overview integration

### Inline annotations

CRITICAL and HIGH issues appear as red error annotations on the exact file and line. MEDIUM and LOW appear as yellow warnings. Visible on the Actions run page, in PR diff views, and in the Files changed tab.

### Job Summary

Every run writes a structured markdown report to the Actions Summary tab showing all issues found, their severity, whether they are auto-fixable, and the suggested fix.

---

## Memory

CIRecon maintains per-repo memory stored in GitHub Actions cache. Each repo's memory is completely isolated.

**What memory does:**

After flagging an issue, CIRecon remembers it. On the next run it skips issues it has already reported — so your Job Summary only shows new things. Issues that keep appearing across three or more runs are automatically escalated in severity.

**How to enable it:**

Add `actions/cache` before the CIRecon step:

```yaml
- uses: actions/cache@v4
  with:
    path: .cirecon-memory
    key: cirecon-memory-${{ github.repository }}
```

Memory persists as long as your repo has activity within 7 days. If the cache expires, CIRecon starts fresh gracefully.

---

## Org-wide dashboard

Scan all your repos on a schedule and publish a health dashboard to a GitHub Gist:

```yaml
name: CIRecon Dashboard

on:
  schedule:
    - cron: '0 9 * * 1'
  workflow_dispatch:

jobs:
  dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: arpita-rathwa/CIRecon@v1
        env:
          CIRECON_GITHUB_TOKEN: ${{ secrets.CIRECON_PAT }}
        with:
          mode: dashboard
          repos: 'owner/repo1,owner/repo2,owner/repo3'
          gist-id: 'your-gist-id-here'
```

Health scores start at 100 and deduct per issue (CRITICAL: −20, HIGH: −10, MEDIUM: −5). The Gist updates automatically on every run.

> Dashboard mode requires a PAT with `repo` and `gist` scopes stored as `CIRECON_PAT`.

---

## Configuration

| Input | Description | Default |
|---|---|---|
| `mode` | `scan` (default) or `dashboard` | `scan` |
| `repos` | Comma-separated repos for dashboard mode | _(required in dashboard mode)_ |
| `gist-id` | Existing Gist ID to update in dashboard mode | _(optional)_ |
| `fail-on-unresolved` | Exit code 1 if issues are found | `false` |

---

## How it compares

| Feature | actionlint | CIRecon |
|---|---|---|
| Syntax and schema validation | ✅ | ✅ |
| Security misconfiguration detection | ❌ | ✅ |
| Runtime behavioral gap detection | ❌ | ✅ |
| GitHub Code Scanning integration (SARIF) | ❌ | ✅ |
| Inline annotations in GitHub UI | ❌ | ✅ |
| Job Summary report | ❌ | ✅ |
| Per-repo memory — no repeated noise | ❌ | ✅ |
| Org-wide health dashboard | ❌ | ✅ |
| Free to use | ✅ | ✅ |

---

## Contributing

Adding a new rule takes about 15 minutes. See [CONTRIBUTING.md](CONTRIBUTING.md) for a step-by-step guide.

Found a bug? Open an issue using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).

---

## License

MIT — see [LICENSE](LICENSE).
