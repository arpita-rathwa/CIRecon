# CIRecon

> Security-aware CI/CD linter for GitHub Actions — detects workflow misconfigurations, auto-fixes what it can, and reports everything directly in your Actions UI.

[![CI](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml/badge.svg)](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/GitHub-Marketplace-orange)](https://github.com/marketplace/actions/cirecon)
[![Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)](https://github.com/arpita-rathwa/CIRecon)

---

## The problem

A misindented YAML block, a deprecated action version, a `needs:` reference pointing to a renamed job, a secret accidentally printed to logs — any of these can silently break your pipeline or expose your infrastructure. CIRecon catches them before they cause damage.

---

## What it does

CIRecon runs automatically on every push to `.github/workflows/`. It:

1. Scans every workflow file with a deterministic rule engine — **7 rules** covering syntax, correctness, and security
2. Auto-fixes everything it can confidently repair
3. Uses an agentic Claude-powered loop for issues that need reasoning
4. Validates every fix before committing — no broken patches ever land
5. Writes a structured **Job Summary** directly in the GitHub Actions UI — no PR noise, no extra permissions
6. Optionally scans your **entire org** and publishes a health dashboard to a GitHub Gist

---

## Quickstart

### Per-repo scan (default)

```yaml
name: CIRecon

on:
  push:
    paths:
      - '.github/workflows/**'

jobs:
  cirecon:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: arpita-rathwa/CIRecon@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Org-wide dashboard

```yaml
name: CIRecon Dashboard

on:
  schedule:
    - cron: '0 9 * * 1'  # every Monday 9am
  workflow_dispatch:

jobs:
  dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: arpita-rathwa/CIRecon@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          mode: dashboard
          repos: 'owner/repo1,owner/repo2,owner/repo3'
          gist-id: ${{ vars.CIRECON_GIST_ID }}
```

> `anthropic-api-key` is optional. Without it, CIRecon runs in rule-engine-only mode and still catches and fixes the majority of issues for free.

---

## What CIRecon checks

### Correctness rules

| Rule | Description | Severity | Auto-fixable |
|---|---|---|---|
| `RULE_DEPRECATED_ACTION` | Actions pinned to outdated versions (e.g. `checkout@v2` → `@v4`). SHA-pinned actions are exempt. | MEDIUM | ✅ Yes |
| `RULE_MISSING_PERMISSIONS_BLOCK` | No top-level `permissions:` block — `GITHUB_TOKEN` gets broad default access. | HIGH | ✅ Yes |
| `RULE_BROKEN_NEEDS_DEPENDENCY` | Job `needs:` references a job ID that doesn't exist. | HIGH | ❌ Manual fix |

### Security rules

| Rule | Description | Severity | Auto-fixable |
|---|---|---|---|
| `RULE_SECRET_IN_RUN_COMMAND` | `${{ secrets.* }}` embedded in `run:` commands — secret values appear in plain text in logs. | CRITICAL | ❌ Manual fix |
| `RULE_PULL_REQUEST_TARGET_UNSAFE` | `pull_request_target` + `actions/checkout` with PR ref — known RCE vector giving untrusted code write access. | CRITICAL | ❌ Manual fix |
| `RULE_OVERLY_BROAD_PERMISSIONS` | `write-all` or 3+ write-level permissions — increases blast radius if workflow is compromised. | HIGH | ❌ Manual fix |
| `RULE_UNPINNED_THIRD_PARTY_ACTION` | Third-party action not pinned to a full 40-char commit SHA — can be silently updated with malicious code. | HIGH | ❌ Manual fix |

More rules welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Job Summary

Every CIRecon run writes a structured report directly to the GitHub Actions UI — no PR needed, no extra permissions, always visible on the run page:

```
## CIRecon Report

Files scanned: 2 | Issues found: 4 | Auto-fixable: 2 | Needs attention: 2

### Issues Found

| File | Rule | Severity | Auto-fixable | Suggested Fix |
|---|---|---|---|---|
| ci.yml | RULE_DEPRECATED_ACTION | MEDIUM | ✅ | actions/checkout@v4 |
| ci.yml | RULE_MISSING_PERMISSIONS_BLOCK | HIGH | ✅ | permissions: contents: read |
| deploy.yml | RULE_SECRET_IN_RUN_COMMAND | CRITICAL | ❌ | Manual fix required |
| deploy.yml | RULE_UNPINNED_THIRD_PARTY_ACTION | HIGH | ❌ | Pin to full SHA |
```

---

## Org-wide dashboard

CIRecon can scan all your repos on a schedule and publish a health dashboard to a GitHub Gist:

```
# CIRecon Org Health Dashboard
Last updated: 2025-07-01 09:00 UTC

## Summary
| Metric | Value |
|---|---|
| Repos scanned | 5 |
| Average health score | 74/100 |
| Critical issues | 2 |
| Clean repos | 1 |

## Repo Health Scores
| Repo | Health Score | Issues | Status |
|---|---|---|---|
| arpita-rathwa/CIRecon | 100/100 | 0 | ✅ Clean |
| arpita-rathwa/LendIQ | 65/100 | 4 | ⚠️ Issues found |
```

Health score starts at 100 and deducts points per issue severity (CRITICAL: -20, HIGH: -10, MEDIUM: -5, LOW: -2).

---

## How it works

```
push event
    → load per-repo memory (.github/cirecon/memory.json)
    → rule engine scans all .github/workflows/*.yml
    → deterministic fixes applied + validated
    → agent loop (Claude) handles remaining issues
    → Job Summary written to Actions UI
    → PR opened if fixes were applied
    → memory updated on PR merge
```

CIRecon is **deterministic-first** — the rule engine always runs before any LLM call. Claude is only invoked for issues static analysis can't resolve confidently, keeping costs low and behaviour predictable.

Per-repo memory means CIRecon gets smarter over time — it won't re-suggest fixes that were previously rejected and recognises recurring patterns.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

---

## Configuration

### Scan mode (default)

| Input | Description | Default |
|---|---|---|
| `github-token` | GitHub token for branch and PR creation | _(required)_ |
| `anthropic-api-key` | Anthropic API key — enables Claude-powered fallback | _(optional)_ |
| `claude-model` | Claude model to use for LLM fallback | `claude-haiku-4-5-20251001` |
| `max-iterations` | Maximum agent loop iterations per run | `10` |
| `fail-on-unresolved` | Exit with error code 1 if issues remain unresolved | `false` |

### Dashboard mode

| Input | Description | Default |
|---|---|---|
| `mode` | Set to `dashboard` to enable org-wide scanning | `scan` |
| `repos` | Comma-separated list of `owner/repo` to scan | _(required)_ |
| `gist-id` | Existing Gist ID to update — omit to create a new one | _(optional)_ |

---

## Why not just use actionlint?

| Feature | actionlint | CIRecon |
|---|---|---|
| Detects syntax issues | ✅ | ✅ |
| Detects security misconfigurations | ❌ | ✅ |
| Auto-fixes issues | ❌ | ✅ |
| LLM fallback for complex issues | ❌ | ✅ |
| Job Summary in Actions UI | ❌ | ✅ |
| Per-repo memory | ❌ | ✅ |
| Org-wide health dashboard | ❌ | ✅ |
| Free to use | ✅ | ✅ |

---

## Contributing

Adding a new rule takes about 15 minutes. See [CONTRIBUTING.md](CONTRIBUTING.md) for a step-by-step guide covering rule implementation, fixtures, and tests.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [@arpita-rathwa](https://github.com/arpita-rathwa)*
