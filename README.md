# CIRecon

> Agentic CI/CD repair for GitHub Actions — detects broken workflow files, auto-fixes what it can, and opens a PR with the rest.

[![CI](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml/badge.svg)](https://github.com/arpita-rathwa/CIRecon/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/GitHub-Marketplace-orange)](https://github.com/marketplace/actions/cirecon)

---

## The problem

A misindented YAML block, a deprecated action version, a `needs:` reference pointing to a renamed job — any of these silently breaks your entire pipeline. You push, CI fails, you read the logs, you edit the YAML, you push again. CIRecon eliminates this loop.

---

## What it does

CIRecon runs automatically when you push changes to `.github/workflows/`. It:

1. Scans every workflow file with a deterministic rule engine
2. Auto-fixes everything it can confidently repair
3. Uses an agentic Claude-powered loop for issues that need reasoning
4. Validates every fix before committing — no broken patches ever land
5. Opens a pull request with a structured summary of what was fixed and what needs your attention

You review, you merge. CIRecon never touches your main branch directly.

---

## Quickstart

Add this to any workflow file in your repo:

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
      - uses: arpita-rathwa/CIRecon@v1
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

> `anthropic-api-key` is optional. Without it, CIRecon runs in rule-engine-only mode — still fixes the majority of common issues for free.

---

## What CIRecon checks

| Rule | Description | Auto-fixable |
|---|---|---|
| `RULE_DEPRECATED_ACTION` | Detects actions pinned to outdated versions (e.g. `checkout@v2` → `@v4`). Skips SHA-pinned actions intentionally. | ✅ Yes |
| `RULE_MISSING_PERMISSIONS_BLOCK` | Flags workflows with no top-level `permissions:` block. Without it, `GITHUB_TOKEN` has broad default access. | ✅ Yes |
| `RULE_BROKEN_NEEDS_DEPENDENCY` | Catches jobs with `needs:` entries referencing job IDs that don't exist — a common cause of silent pipeline breakage. | ❌ No — flagged for human review |

More rules coming in v2 — see [CONTRIBUTING.md](CONTRIBUTING.md) to add your own.

---

## How it works

```
push event
    → rule engine scans all .github/workflows/*.yml
    → deterministic fixes applied + validated
    → agent loop (Claude) handles remaining issues
    → pull request opened with full audit trail
```

CIRecon is designed **deterministic-first** — the rule engine runs before any LLM call. Claude is only invoked for issues that static analysis can't resolve with confidence. This keeps costs low and behaviour predictable.

Per-repo memory at `.github/cirecon/memory.json` means CIRecon learns from past runs — it won't re-suggest fixes that were previously rejected, and it recognises recurring patterns over time.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

---

## Configuration

| Input | Description | Default |
|---|---|---|
| `anthropic-api-key` | Anthropic API key — enables Claude-powered fallback for issues the rule engine can't fix | _(optional)_ |
| `max-iterations` | Maximum agent loop iterations per run | `10` |
| `fail-on-unresolved` | Exit with code 1 if any issues remain unresolved after repair | `false` |

---

## Example PR

When CIRecon finds and fixes issues, it opens a PR like this:

```
[CIRecon] Auto-fix 3 CI/CD workflow issue(s)

Files scanned: 2
Issues found: 3
Issues auto-fixed: 2
Requires human attention: 1

Fixed Issues
─────────────────────────────────────────────────
deploy.yml  | RULE_DEPRECATED_ACTION       | actions/checkout@v2 → @v4   | ✅
test.yml    | RULE_MISSING_PERMISSIONS_BLOCK| Added permissions block      | ✅

Unresolved Issues
─────────────────────────────────────────────────
release.yml | RULE_BROKEN_NEEDS_DEPENDENCY | Job 'deploy' needs 'build'
              which does not exist — please fix manually
```

---

## Why not just use actionlint?

`actionlint` is a great static linter — CIRecon respects it. The difference:

| | actionlint | CIRecon |
|---|---|---|
| Detects issues | ✅ | ✅ |
| Auto-fixes issues | ❌ | ✅ |
| Opens a PR with fixes | ❌ | ✅ |
| LLM fallback for complex issues | ❌ | ✅ |
| Per-repo memory | ❌ | ✅ |
| Free to use | ✅ | ✅ |

---

## Contributing

CIRecon is designed to be extended. Adding a new rule takes about 15 minutes — see [CONTRIBUTING.md](CONTRIBUTING.md) for a step-by-step guide.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [@arpita-rathwa](https://github.com/arpita-rathwa)*
