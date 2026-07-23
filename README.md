
# CIRecon

A GitHub Code Scanning provider for GitHub Actions workflow files. Detects security misconfigurations, correctness errors, and runtime behavioral gaps. Outputs SARIF for permanent integration with GitHub's Security tab.

[![CI](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml/badge.svg)](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/GitHub-Marketplace-orange)](https://github.com/marketplace/actions/cirecon)
[![Coverage](https://img.shields.io/badge/coverage-81%25-brightgreen)](https://github.com/arpita-rathwa/CIRecon)

---

## Overview

CIRecon runs as a GitHub Action on every push and pull request targeting workflow files. It performs static analysis using a 10-rule engine across three categories — correctness, security, and runtime behavioral gaps — and produces three output artifacts:

- **SARIF file** uploaded to GitHub's Code Scanning API, appearing permanently in the Security tab with tracking, dismissals, and PR integration
- **Inline annotations** on the exact file and line via GitHub workflow commands
- **Job Summary** written to `$GITHUB_STEP_SUMMARY`

CIRecon maintains per-repo memory via GitHub Actions cache, filtering previously reported issues from subsequent runs and escalating issues that recur across three or more runs.

---

## Installation

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

`permissions: security-events: write` is required for SARIF upload. `if: always()` ensures findings are uploaded regardless of exit code. The `actions/cache` step enables cross-run memory persistence.

See [`examples/cirecon.yml`](examples/cirecon.yml) for the full reference configuration.

---

## Rules

### Correctness

| Rule ID | Description | Severity | Auto-fixable |
|---|---|---|---|
| `RULE_DEPRECATED_ACTION` | Action pinned to an outdated version tag. SHA-pinned actions are exempt. | MEDIUM | ✅ |
| `RULE_MISSING_PERMISSIONS_BLOCK` | No top-level `permissions:` block — `GITHUB_TOKEN` receives overly broad default scopes. | HIGH | ✅ |
| `RULE_BROKEN_NEEDS_DEPENDENCY` | `needs:` references a job ID not defined in the workflow. | HIGH | ❌ |

### Security

| Rule ID | Description | Severity | Auto-fixable |
|---|---|---|---|
| `RULE_SECRET_IN_RUN_COMMAND` | `${{ secrets.* }}` interpolated inside a `run:` step — value is exposed in plain text in run logs. | CRITICAL | ❌ |
| `RULE_PULL_REQUEST_TARGET_UNSAFE` | `pull_request_target` trigger combined with checkout of the PR head ref — grants untrusted code write access to the repository. | CRITICAL | ❌ |
| `RULE_OVERLY_BROAD_PERMISSIONS` | `write-all` or three or more write-level permission scopes defined at workflow or job level. | HIGH | ❌ |
| `RULE_UNPINNED_THIRD_PARTY_ACTION` | Third-party action referenced by version tag rather than a full 40-character commit SHA. | HIGH | ❌ |

### Runtime Behavioral

These rules model the behavioral difference between `push` and `pull_request` event contexts — specifically token permission scope, secret availability, and `github.ref` value. They are not detectable by syntax-only analysis.

| Rule ID | Description | Severity | Auto-fixable |
|---|---|---|---|
| `RULE_FORK_PR_SECRET_EXPOSURE` | `pull_request` workflow references secrets — secrets are unavailable in fork PR contexts and resolve to empty strings without error. | HIGH | ❌ |
| `RULE_WRITE_STEP_ON_FORK_TRIGGER` | Step requiring write permissions in a `pull_request` workflow — fork PRs receive a read-only token, causing silent failure. | HIGH | ❌ |
| `RULE_REF_CONDITION_MISMATCH` | `if: github.ref == 'refs/heads/...'` in a workflow triggered by both `push` and `pull_request` — evaluates to false on all PR runs, causing the step to silently skip. | MEDIUM | ❌ |

---

## Output

### SARIF / Code Scanning

CIRecon serializes all findings to SARIF 2.1.0 format at `cirecon-results.sarif`. When uploaded via `github/codeql-action/upload-sarif`, findings are visible in **Security → Code Scanning** with:

- Persistent tracking across commits and branches
- PR check integration showing new findings introduced per PR
- Dismissal support with audit trail
- Inclusion in GitHub's org-level Security Overview

SARIF upload is free for public repositories. Private repositories require GitHub Advanced Security.

### Inline Annotations

Findings are printed to stdout as GitHub workflow commands:

```
::error file=.github/workflows/ci.yml,line=12,title=RULE_SECRET_IN_RUN_COMMAND::...
::warning file=.github/workflows/ci.yml,line=8,title=RULE_DEPRECATED_ACTION::...
```

CRITICAL and HIGH map to `::error`. MEDIUM and LOW map to `::warning`. Annotations are visible on the Actions run page, in PR diff views, and in the Files changed tab. No additional permissions required.

### Job Summary

A structured Markdown table is written to `$GITHUB_STEP_SUMMARY` on every run, listing all detected issues with file, rule ID, severity, auto-fixable status, and suggested fix. No additional permissions required.

---

## Memory

CIRecon persists state between runs at `.cirecon-memory/memory.json` using GitHub Actions cache.

**Behavior:**

- Issues reported in the last 5 runs are filtered from the current run's output — eliminating repeated reporting of acknowledged but unfixed issues
- Issues detected in 3 or more runs are escalated: MEDIUM → HIGH, HIGH → CRITICAL, with a `[RECURRING]` suffix appended to the message

Memory is scoped per repository via the cache key `cirecon-memory-${{ github.repository }}`. Cache entries expire after 7 days of repository inactivity; CIRecon reinitialises gracefully on expiry.

Memory requires the `actions/cache` step shown in the installation section.

---

## Dashboard Mode

Scans multiple repositories in a single run and publishes aggregated health scores to a GitHub Gist.

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

Health scores are computed starting at 100, with deductions of 20 per CRITICAL, 10 per HIGH, and 5 per MEDIUM finding. The Gist is updated on every run.

Requires a classic PAT with `repo` and `gist` scopes, stored as `CIRECON_PAT`.

---

## Configuration

| Input | Description | Default |
|---|---|---|
| `mode` | Execution mode: `scan` or `dashboard` | `scan` |
| `repos` | Comma-separated `owner/repo` list for dashboard mode | _(required in dashboard mode)_ |
| `gist-id` | Gist ID to update in dashboard mode — creates new if omitted | _(optional)_ |
| `fail-on-unresolved` | Exit with code 1 when findings are detected | `false` |
| `github-token` | GitHub token for dashboard mode repo cloning | _(optional)_ |

---

## Local Development

```bash
git clone https://github.com/arpita-rathwa/CIRecon
cd CIRecon
pip install -e ".[dev]"

# scan current directory
cirecon

# run test suite
pytest tests/ -v --cov=cirecon --cov-fail-under=80

# lint
ruff check cirecon/
```

---

## Comparison

| Capability | actionlint | CIRecon |
|---|---|---|
| YAML syntax and schema validation | ✅ | ✅ |
| Security misconfiguration detection | ❌ | ✅ |
| Runtime behavioral gap detection | ❌ | ✅ |
| SARIF output / GitHub Code Scanning | ❌ | ✅ |
| Inline annotations with line precision | ❌ | ✅ |
| Job Summary | ❌ | ✅ |
| Adaptive per-repo memory | ❌ | ✅ |
| Org-wide health dashboard | ❌ | ✅ |
| Local CLI | ❌ | ✅ |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for instructions on adding rules, running tests, and submitting pull requests.

Bug reports: [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md)

---

## License






