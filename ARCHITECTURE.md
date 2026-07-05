# CIRecon Architecture

> A deterministic-first, security-aware, agent-assisted GitHub Action for CI/CD workflow repair and org-wide health monitoring.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Architecture Layers](#3-architecture-layers)
4. [Memory Layer](#4-memory-layer)
5. [Dashboard Mode](#5-dashboard-mode)
6. [End-to-End Data Flow](#6-end-to-end-data-flow)
7. [Technology Stack](#7-technology-stack)
8. [Design Decisions and Tradeoffs](#8-design-decisions-and-tradeoffs)
9. [Security](#9-security)
10. [Scalability](#10-scalability)
11. [Known Limitations](#11-known-limitations)
12. [Future Roadmap](#12-future-roadmap)
13. [Mermaid Diagrams](#13-mermaid-diagrams)

---

## 1. System Overview

### What CIRecon Is

CIRecon is an open-source GitHub Action that automatically scans `.github/workflows/*.yml` files, detects CI/CD configuration errors and security misconfigurations using a rule-based static analysis engine, and — when deterministic analysis cannot resolve an issue — invokes the Claude API through a structured tool-calling loop to reason about repairs. Every run writes a structured **Job Summary** directly to the GitHub Actions UI. CIRecon also supports an org-wide dashboard mode that scans multiple repositories and publishes a health score report to a GitHub Gist.

### The Problem It Solves

Broken CI/CD pipelines are disproportionately expensive relative to their root causes. A misindented YAML block, a deprecated action version, a missing `permissions` key, or a `needs:` reference pointing to a renamed job can silently block an entire team's deployment pipeline. More seriously, security misconfigurations — secrets printed to logs, dangerous `pull_request_target` patterns, overly broad permissions — can expose infrastructure to attack without any visible failure.

CIRecon eliminates both problems. It detects mechanically fixable errors and fixes them, detects security misconfigurations and explains them, and surfaces everything in a structured Job Summary directly on the Actions run page — no PR noise, no extra permissions required.

### Intended Users

- Individual developers who maintain repositories with GitHub Actions workflows
- Security-conscious teams who want automated CI/CD hygiene without a paid SaaS
- Open-source maintainers managing multiple repositories
- MLOps engineers running GPU-intensive or artifact-heavy CI pipelines
- Platform teams who want org-wide visibility into CI/CD health

### High-Level Execution Lifecycle

**Scan mode (default):**
1. A push event modifies a file under `.github/workflows/`
2. GitHub spins up a runner and executes the CIRecon Docker action
3. CIRecon loads repo-scoped memory from `.github/cirecon/memory.json` (if it exists)
4. CIRecon reads all workflow files in the repository
5. The rule engine runs all 7 checks and categorizes every issue by fixability
6. Memory is consulted — previously rejected fixes are skipped
7. All auto-fixable issues are patched, validated, and committed via git subprocess
8. Remaining issues are passed to the agent loop (if API key present)
9. A **Job Summary** is written to `$GITHUB_STEP_SUMMARY` with the full issue table
10. Memory is updated on PR merge

**Dashboard mode:**
1. A scheduled or manual trigger fires
2. CIRecon clones each repo in the specified list (shallow, depth=1)
3. Runs all 7 rules against every workflow file in each repo
4. Computes a health score per repo
5. Generates a markdown dashboard and publishes to a GitHub Gist
6. Writes the dashboard to Job Summary as well

### Major Architectural Principles

- **Deterministic first.** The rule engine always runs before any LLM call.
- **Job Summary as primary output.** Every run produces a visible, structured report in the Actions UI with zero extra permissions.
- **LLM as bounded fallback.** The agent loop is constrained by max iterations, a validation gate, and explicit stopping conditions.
- **BYO key.** CIRecon never manages API keys. Each user provides their own.
- **No commits without validation.** Every patch passes a 3-stage validation gate before being written to disk.
- **Security-aware.** Four of the seven rules target security misconfigurations, not just syntax errors.

### Design Goals

- Zero running cost for the project maintainer
- Useful in rule-engine-only mode with no API key
- Transparent: every issue explained in Job Summary with exact fix
- Safe: validation gate prevents committing broken YAML
- Extensible: new rules are single Python functions
- Adaptive: per-repo memory improves accuracy over time
- Org-visible: dashboard mode gives a cross-repo health overview

### Non-Goals

- CIRecon does not review application code
- CIRecon does not merge PRs automatically
- CIRecon does not create or manage GitHub Secrets
- CIRecon does not support GitLab CI or CircleCI in v1
- CIRecon does not guarantee semantic correctness of complex workflow business logic

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Repository                           │
│  Push / PR Event → .github/workflows/*.yml modified             │
│  Memory → .github/cirecon/memory.json                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ triggers
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions Runner                        │
│  Docker container spun up, action.yml entry point executed      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Mode Router (main.py)                           │
│  MODE=scan → run()   |   MODE=dashboard → run_dashboard()       │
└────────────┬──────────────────────────┬────────────────────────┘
             │ scan                      │ dashboard
             ▼                           ▼
┌────────────────────┐     ┌────────────────────────────────────┐
│   Memory Layer     │     │      org_scanner.py                │
│   Load memory.json │     │  Clone repos → run rule engine     │
└────────┬───────────┘     │  Compute health scores             │
         │                 └──────────────┬─────────────────────┘
         ▼                                │
┌────────────────────┐                   ▼
│   Input Layer      │     ┌────────────────────────────────────┐
│   Discover YAMLs   │     │      dashboard.py                  │
└────────┬───────────┘     │  Generate markdown                 │
         │                 │  Publish to GitHub Gist            │
         ▼                 └──────────────┬─────────────────────┘
┌────────────────────┐                   │
│   Rule Engine      │                   │
│   7 rules          │                   │
│   correctness +    │                   │
│   security         │                   │
└────────┬───────────┘                   │
         │                               │
         ▼                               │
┌────────────────────┐                   │
│   Fix Applier      │                   │
│   In-memory only   │                   │
└────────┬───────────┘                   │
         │                               │
         ▼                               │
┌────────────────────┐                   │
│   Validation Layer │                   │
│   3-stage gate     │                   │
└────────┬───────────┘                   │
         │                               │
         ▼                               │
┌────────────────────┐                   │
│   Agent Loop       │                   │
│   Claude API       │                   │
│   Tool-calling     │                   │
└────────┬───────────┘                   │
         │                               │
         ▼                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Output Layer                               │
│  Job Summary ($GITHUB_STEP_SUMMARY) — always                    │
│  Git commit + PR — when fixes applied                           │
│  Gist publish — dashboard mode                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Layers

### Trigger Layer

CIRecon is packaged as a Docker container action. The `action.yml` manifest defines inputs and passes them as environment variables into the container.

**Inputs:**

```yaml
inputs:
  github-token:
    required: true
  anthropic-api-key:
    required: false
  claude-model:
    default: 'claude-haiku-4-5-20251001'
  max-iterations:
    default: '10'
  fail-on-unresolved:
    default: 'false'
  mode:
    default: 'scan'
  repos:
    required: false   # dashboard mode only
  gist-id:
    required: false   # dashboard mode only
```

**Why Docker over composite action:** Docker guarantees a fixed, reproducible Python environment. Composite actions inherit the runner's Python version and system libraries, causing subtle dependency conflicts across runner types.

**Permissions required (scan mode):**
```yaml
permissions:
  contents: write
  pull-requests: write
```

---

### Input Layer

Discovers all `.github/workflows/*.yml` and `.github/workflows/*.yaml` files using `pathlib.Path.glob()`. Each file is parsed into a `WorkflowFile` object containing the raw string, PyYAML parse result, and ruamel.yaml parse result. The GitHub Actions JSON schema is fetched from SchemaStore once per run and cached in memory.

---

### Rule Engine (Deterministic Layer)

Seven independent rule functions run against each parsed workflow file. Each returns a list of `Issue` objects.

**Issue schema:**
```python
@dataclass
class Issue:
    id: str
    severity: Severity        # LOW | MEDIUM | HIGH | CRITICAL
    message: str
    location: Location        # file, line, column
    auto_fixable: bool
    confidence: float         # 0.0–1.0
    suggested_fix: Optional[str]
```

**All rules:**

| Rule ID | Description | Severity | Auto-fixable | Confidence |
|---|---|---|---|---|
| `RULE_DEPRECATED_ACTION` | Action pinned to outdated version. SHA-pinned actions exempt. | MEDIUM | ✅ | 1.0 |
| `RULE_MISSING_PERMISSIONS_BLOCK` | No top-level `permissions:` block | HIGH | ✅ | 0.9 |
| `RULE_BROKEN_NEEDS_DEPENDENCY` | `needs:` references non-existent job ID | HIGH | ❌ | 1.0 |
| `RULE_SECRET_IN_RUN_COMMAND` | `${{ secrets.* }}` in `run:` step — leaks to logs | CRITICAL | ❌ | 0.95 |
| `RULE_PULL_REQUEST_TARGET_UNSAFE` | `pull_request_target` + checkout of PR ref — RCE vector | CRITICAL | ❌ | 0.9 |
| `RULE_OVERLY_BROAD_PERMISSIONS` | `write-all` or 3+ write-level permission scopes | HIGH | ❌ | 1.0 |
| `RULE_UNPINNED_THIRD_PARTY_ACTION` | Third-party action not pinned to 40-char SHA | HIGH | ❌ | 1.0 |

**Why deterministic analysis precedes LLM reasoning:** The rule engine is free, fast, and 100% reproducible. Calling an LLM for `checkout@v2 → @v4` wastes tokens on a problem that pattern matching solves perfectly. The LLM is only invoked when the issue list contains items the rule engine cannot confidently fix.

---

### Fix Applier

Applies patches **in memory only** — never writes to disk until all fixes for a file have been accumulated and validated.

**Sequential accumulation (critical correctness requirement):**
```python
current_content = original_content
for issue in file_issues:
    patched = apply_fix(current_content, issue)
    if validate_all(path, patched, original_issues).passed:
        current_content = patched  # next fix builds on this
```

Each fix operates on the output of the previous fix, not the original. This prevents a class of corruption bugs where fix N overwrites the result of fix N-1.

**`RULE_DEPRECATED_ACTION` fix:** Extracts the exact deprecated string from `issue.message` and uses `str.replace(old, new, 1)` — targeting only the specific occurrence, not all occurrences of the action name.

**`RULE_MISSING_PERMISSIONS_BLOCK` fix:** Uses `re.sub(r"^(\s*)jobs:", ..., flags=re.MULTILINE)` to anchor the match to the start of a line, preventing false matches inside comments or string values.

**Why not ruamel.yaml for fixes:** The fixes CIRecon applies are targeted string-level replacements. Using ruamel.yaml's round-trip parser adds complexity without meaningful benefit for these specific transformations. ruamel.yaml is reserved for future fixes that require structural YAML manipulation.

---

### Validation Layer

Every proposed patch passes three checks before being accepted:

1. **YAML syntax** — `yaml.safe_load()` confirms the patched file is valid YAML
2. **Schema conformance** — `jsonschema.validate()` checks against the GitHub Actions JSON schema from SchemaStore. False positives on `if:` expressions (schema validator misinterprets them) are filtered out.
3. **Rule engine re-check** — `run_all_checks()` runs again on the patched content. Only issues with `id+file` combinations not present in the original issue list count as "newly introduced."

A patch is committed only if all three pass. If any check fails, the patch is discarded and the issue is marked unresolved.

---

### Agent Loop

When unresolved issues remain after the rule engine and `ANTHROPIC_API_KEY` is present, the agent loop activates.

**State object:**
```python
@dataclass
class AgentState:
    scanned_files: list[str]
    issues_found: list[Issue]
    issues_fixed: list[Issue]
    unresolved: list[Issue]
    iteration: int
    tool_history: list[dict]
    patches: list[dict]
    validation_results: list[ValidationResult]
```

**Tool definitions** (passed to Claude via tool-calling API):
- `read_workflow_file` — reads a file from disk
- `validate_yaml_schema` — validates content against schema
- `run_rule_checks` — runs deterministic rules on content
- `check_secret_exists` — checks GitHub API for secret existence
- `propose_fix` — calls Claude to draft a YAML patch
- `apply_fix` — applies a patch in memory
- `create_branch_and_pr` — commits fixes and opens PR

**Stopping conditions:** zero unresolved issues, non-fixable issue flagged, same tool+args called twice (infinite loop guard), max iterations reached, API error.

**Configurable model:** The Claude model is configurable via the `claude-model` input (default: `claude-haiku-4-5-20251001`). Use Haiku for most cases (cheap, fast). Switch to Sonnet for complex security issues requiring deeper reasoning.

---

### GitHub Integration Layer

CIRecon uses **git subprocess commands** (not the GitHub Contents API) for committing workflow file changes. The GitHub Contents API returns 403 when writing to `.github/workflows/` — a hard GitHub security policy. Git subprocess bypasses this:

```python
subprocess.run(["git", "config", "user.email", "cirecon@github.com"])
subprocess.run(["git", "config", "user.name", "CIRecon"])
subprocess.run(["git", "checkout", "-B", branch_name])
subprocess.run(["git", "add", ".github/workflows/"])
subprocess.run(["git", "commit", "-m", "[CIRecon] Auto-fix CI/CD workflow issues"])
remote_url = f"https://x-access-token:{github_token}@github.com/{repo}.git"
subprocess.run(["git", "push", remote_url, branch_name])
```

PR creation uses the GitHub REST API via `requests` after the branch is pushed.

**CIRecon's own workflow file is never patched** — any file with `cirecon` in its path is filtered out of the patch list before committing, preventing CIRecon from corrupting its own trigger file.

---

### Output Layer

**Primary output — Job Summary:**

Every run writes a markdown report to `$GITHUB_STEP_SUMMARY`:

```python
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
    f.write("## CIRecon Report\n\n")
    f.write(f"**Files scanned:** {n} | **Issues found:** {n} | ...\n\n")
    f.write("| File | Rule | Severity | Auto-fixable | Suggested Fix |\n")
    # one row per issue
```

This requires zero permissions, zero API calls, and is always visible on the Actions run page regardless of whether fixes were applied or PRs were opened.

**Secondary output — Git commit + PR (when fixes applied):**

When auto-fixable issues exist, CIRecon writes fixed files atomically, commits via git subprocess, and opens a PR via the GitHub REST API.

**Tertiary output — GitHub Gist (dashboard mode):**

The dashboard markdown is published to a Gist via `PATCH /gists/{id}` (update) or `POST /gists` (create). The Gist URL is printed to the run log and also appended to the Job Summary.

---

## 4. Memory Layer

### Overview

CIRecon maintains a persistent, repo-scoped memory store at `.github/cirecon/memory.json`. Every repo gets its own completely isolated memory file. Memory is only updated when a fix PR is merged — not on every scan run — eliminating git commit noise.

### Memory Schema

```json
{
  "repo": "owner/repo",
  "created_at": "2025-01-15T10:00:00Z",
  "last_run": "2025-07-01T14:32:00Z",
  "total_runs": 12,
  "fixes": [
    {
      "issue_id": "RULE_DEPRECATED_ACTION",
      "file": "deploy.yml",
      "fix_applied": "actions/checkout@v2 → @v4",
      "pr_url": "https://github.com/.../pull/42",
      "pr_status": "merged"
    }
  ],
  "rejected_fixes": ["RULE_MISSING_PERMISSIONS_BLOCK"],
  "known_secrets": ["ANTHROPIC_API_KEY", "GITHUB_TOKEN"],
  "repo_preferences": {
    "preferred_runner": "ubuntu-latest"
  }
}
```

### Merge-triggered updates

```
push → CIRecon scans → opens fix PR (no memory write)
                              ↓
              human reviews + merges PR
                              ↓
      pull_request closed + merged: true event
                              ↓
      CIRecon updates memory.json (one commit, meaningful)
```

### Why in-repo JSON

In-repo JSON is the only approach requiring zero external infrastructure, fully auditable via git history, isolated per repo by definition, and with no expiry or size limits. The one commit per merged PR is a meaningful, reviewable record of accepted fixes — not noise.

---

## 5. Dashboard Mode

### Overview

Dashboard mode scans multiple repositories in a single run and publishes a health score report. It is designed for platform teams or individual developers who want a weekly overview of CI/CD health across all their repos.

### org_scanner.py

```python
@dataclass
class RepoReport:
    repo: str
    files_scanned: int
    issues: list[Issue]
    health_score: int   # 0–100
    scanned_at: str
```

**Health score calculation:**
- Start at 100
- CRITICAL issue: -20
- HIGH issue: -10
- MEDIUM issue: -5
- LOW issue: -2
- Minimum: 0

**Scanning process:**
1. `git clone --depth 1 https://x-access-token:{token}@github.com/{repo}.git {tmpdir}`
2. `discover_workflow_files(tmpdir)` — find all workflow YAMLs
3. `run_all_checks(path, content)` — run all 7 rules
4. Calculate health score from issue list
5. Clean up temp directory

### dashboard.py

Generates a markdown report and publishes to a GitHub Gist.

**Update existing Gist:** `PATCH /gists/{gist_id}` — used on recurring scheduled runs so the same Gist URL stays stable.

**Create new Gist:** `POST /gists` — used on first run. The returned Gist ID should be stored as a repo variable (`CIRECON_GIST_ID`) for subsequent runs.

---

## 6. End-to-End Data Flow

**Scan mode:**

```
1.  GitHub push event → CIRecon action starts
2.  Memory Layer: load .github/cirecon/memory.json
3.  Input Layer: discover all .github/workflows/*.yml
4.  Rule Engine: run 7 rules → List[Issue] with auto_fixable flags
5.  Fix Applier: for each file, accumulate fixes sequentially in memory
6.  Validation Layer: 3-stage check per patch → accept or discard
7.  Agent Loop (if API key + unresolved): Claude tool-calling → more fixes
8.  Output Layer:
    a. Write Job Summary to $GITHUB_STEP_SUMMARY (always)
    b. If patches: write files atomically → git commit → push → open PR
9.  Exit 0 (or 1 if fail-on-unresolved=true and issues remain)
```

**Dashboard mode:**

```
1.  Scheduled/manual trigger → CIRecon action starts (mode=dashboard)
2.  org_scanner: for each repo in REPOS list:
    a. git clone --depth 1
    b. discover_workflow_files
    c. run_all_checks → issues
    d. calculate health score
    e. clean up temp dir
3.  dashboard: generate markdown from RepoReport list
4.  dashboard: publish to GitHub Gist (update or create)
5.  Output Layer: write dashboard to Job Summary
6.  Print Gist URL to run log
```

---

## 7. Technology Stack

| Component | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | Match clause syntax; standard ML/DevOps ecosystem |
| LLM SDK | `requests` (raw HTTP) | Full control over API calls; no SDK dependency |
| YAML parsing | `PyYAML` | Fast, standard; sufficient for read-only parsing and fix application |
| Schema validation | `jsonschema` | Official JSON Schema draft-07 support |
| GitHub API client | `PyGithub` + `requests` | PyGithub for PR creation; raw requests for secrets check |
| Git operations | `subprocess` | Only approach that bypasses GitHub's Contents API restriction on workflow files |
| Action packaging | Docker container | Reproducible environment regardless of runner type |
| Testing | `pytest` + `unittest.mock` | Industry standard; mock-based isolation of all external calls |
| Coverage | `pytest-cov` | Enforced minimum 80% threshold in CI |
| Linting | `ruff` | Fast, modern Python linter |
| CI for CIRecon | GitHub Actions | Dogfoods its own tooling |
| Workflow schema | SchemaStore `github-workflow.json` | Authoritative, community-maintained |
| Memory store | In-repo JSON | Zero infrastructure, version-controlled, repo-isolated |
| Dashboard store | GitHub Gist | Zero infrastructure, shareable, updatable via API |

---

## 8. Design Decisions and Tradeoffs

**Job Summary as primary output over PR:**
The GitHub Contents API returns 403 for workflow files regardless of token permissions — a hard GitHub security policy. Rather than fighting this with git subprocess complexity for every run, Job Summary was adopted as the primary output. It requires zero permissions, always works, and is immediately visible on the Actions run page. PRs remain available for when auto-fixes are applied, using git subprocess to bypass the Contents API restriction.

**Git subprocess over Contents API:**
The Contents API cannot write to `.github/workflows/`. Git subprocess can. The tradeoff is that subprocess calls are harder to test (require mocking) and less portable than API calls, but this is the only reliable approach for workflow file modification.

**Seven rules over comprehensive coverage:**
Seven carefully chosen rules covering the most common and most dangerous workflow issues provide more value than a larger set of marginal rules. Each rule is independently testable, has clear fix semantics, and addresses a documented real-world failure mode.

**Security rules as non-auto-fixable:**
Security misconfigurations (`RULE_SECRET_IN_RUN_COMMAND`, `RULE_PULL_REQUEST_TARGET_UNSAFE`) are flagged but not auto-fixed. Auto-fixing security issues without human review is itself a security risk — the correct remediation depends on intent, which CIRecon cannot infer.

**Haiku as default Claude model:**
Claude Haiku is ~20x cheaper than Sonnet with acceptable quality for the structured YAML repair tasks CIRecon uses it for. Users who need higher-quality fixes for complex issues can switch to Sonnet via the `claude-model` input.

**Dashboard via Gist over GitHub Pages:**
Gist requires no repo configuration, no Pages setup, and works for private repos. The single Gist URL is stable across updates (via PATCH). GitHub Pages would require a dedicated repo and Pages configuration — friction that prevents adoption.

---

## 9. Security

**Least privilege:** CIRecon requests only `contents: write` and `pull-requests: write`. No admin or org-level permissions.

**GitHub Secrets:** All API keys are passed as GitHub Secrets and never logged, never embedded in output, never passed to Claude as raw strings.

**Prompt injection mitigation:** CIRecon passes structured, parsed issue fields to Claude — not raw workflow file content. Free-form YAML content is only passed in `propose_fix`, where Claude is constrained to output only a YAML block.

**Self-exclusion:** CIRecon never patches its own trigger workflow file (`cirecon.yml` is filtered from all patch lists before committing).

**Validation before commit:** Every patch passes a 3-stage validation gate. A patch that introduces a new issue is rejected and the original file is restored from memory — no broken YAML ever lands.

**No source code retention:** CIRecon does not send application code to any external service. Only workflow YAML sections are sent to Claude API.

**Git authentication:** The GitHub token is used only for the git push remote URL and is never written to disk or logged.

---

## 10. Scalability

**Large repositories:** CIRecon processes only `.github/workflows/` files, not the full repository. Even large monorepos typically have fewer than 20 workflow files.

**Dashboard mode:** Repos are scanned sequentially to avoid GitHub API rate limits. Each clone is a shallow clone (`--depth 1`) to minimise bandwidth and time. Temp directories are cleaned up after each repo scan.

**Claude token limits:** Only the relevant file section (±50 lines around the issue location) is sent to `propose_fix`, not the full file. Tool history is summarized after 5 iterations to prevent context overflow.

**Performance expectations:**
- Rule engine only: 2–5 seconds per repository
- With agent loop: 15–60 seconds depending on unresolved issue count and Claude API latency
- Dashboard mode: ~10–30 seconds per repository scanned

---

## 11. Known Limitations

**Cannot guarantee semantic correctness:** CIRecon validates structure, not intent. A structurally valid workflow that deploys to the wrong environment is out of scope.

**Cannot repair broken third-party actions:** If a referenced action has been deleted from the Marketplace, CIRecon detects the reference but cannot propose a valid replacement.

**Cannot create missing secrets:** `RULE_SECRET_IN_RUN_COMMAND` can flag secret references in run commands but cannot create or rotate the secrets themselves.

**Human approval always required:** CIRecon opens PRs. It never merges. Every fix requires human review.

**Agent loop is non-deterministic:** The rule engine produces identical output for identical input. The agent loop does not — two runs on the same unresolved issue may produce different patches.

**Memory quality depends on PR feedback:** If a PR is closed without merge for reasons unrelated to fix quality, CIRecon cannot distinguish this from rejection and may incorrectly record the fix as rejected.

**Dashboard mode is sequential:** Repos are scanned one at a time. For large org-wide scans (20+ repos), this can take several minutes.

---

## 12. Future Roadmap

**More rules (v2):**
- `RULE_MISSING_CHECKOUT_STEP` — job operates on files without checkout
- `RULE_INVALID_RUNS_ON` — unrecognised runner label
- `RULE_DUPLICATE_JOB_ID` — two jobs share an ID
- `RULE_INVALID_MATRIX_SYNTAX` — malformed strategy matrix

**ML pipeline validation:**
- DVC pipeline YAML checks
- GPU runner validation
- Model artifact caching checks

**Cross-repo workflow drift detection:**
- Define a "golden template" workflow
- Flag repos that have drifted from the standard pattern

**GitHub App (v3):**
- Removes all token permission restrictions
- Enables PR creation without git subprocess complexity
- Enables org-wide installation without per-repo setup

**Extended platform support:**
- GitLab CI (`.gitlab-ci.yml`)
- CircleCI (`.circleci/config.yml`)
- Azure Pipelines (`azure-pipelines.yml`)

**Local CLI mode:**
```
pip install cirecon
cirecon scan .
cirecon fix .
cirecon dashboard --repos owner/repo1,owner/repo2
```

---

## 13. Mermaid Diagrams

### Overall Architecture

```mermaid
flowchart LR
    A[GitHub Push / PR Event] --> B[GitHub Actions Runner]
    B --> C[CIRecon Action\nDocker Container]
    C --> D{Mode?}
    D -- scan --> E[Memory Layer\nLoad memory.json]
    D -- dashboard --> F[org_scanner.py\nClone + scan repos]
    E --> G[Input Layer\nDiscover YAMLs]
    G --> H[Rule Engine\n7 rules]
    H --> I[Fix Applier\nIn-memory accumulation]
    I --> J[Validation Layer\n3-stage gate]
    J --> K[Agent Loop\nClaude API optional]
    K --> L[Output Layer]
    F --> M[dashboard.py\nGenerate + publish Gist]
    M --> L
    L --> N[Job Summary\nalways]
    L --> O[Git commit + PR\nwhen fixes applied]
    L --> P[GitHub Gist\ndashboard mode]
```

---

### Agent Loop State Machine

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> LOADING: unresolved issues exist + API key present
    LOADING --> REASONING: context built
    REASONING --> TOOL_EXECUTING: Claude selects tool
    TOOL_EXECUTING --> VALIDATING: tool returns result
    VALIDATING --> UPDATING: patch accepted
    VALIDATING --> REASONING: patch rejected, retry
    UPDATING --> REASONING: issues remain
    UPDATING --> DONE: no issues remain
    REASONING --> DONE: max iterations reached
    REASONING --> DONE: same tool called twice
    REASONING --> FAILED: API error
    DONE --> [*]
    FAILED --> [*]
```

---

### Data Flow — Scan Mode

```mermaid
flowchart LR
    A[workflow YAML files] --> B[WorkflowFile objects]
    C[SchemaStore JSON] --> B
    D[memory.json] --> E[MemoryContext]
    B --> F[Issue list\n7 rules]
    E --> F
    F --> G[In-memory patches\naccumulated per file]
    G --> H[Validation Layer]
    H --> I[Validated patches]
    H --> J[Rejected patches\nmark unresolved]
    I --> K[Job Summary\n$GITHUB_STEP_SUMMARY]
    I --> L[Git commit\nsubprocess]
    L --> M[Pull Request\nGitHub API]
    J --> N[Agent Loop\nClaude optional]
    N --> H
```

---

### Data Flow — Dashboard Mode

```mermaid
flowchart TD
    A[REPOS env var\ncomma-separated list] --> B[org_scanner.py]
    B --> C[git clone depth=1\nper repo]
    C --> D[discover_workflow_files]
    D --> E[run_all_checks\n7 rules per file]
    E --> F[RepoReport\nhealth score 0-100]
    F --> G[dashboard.py\ngenerate markdown]
    G --> H{gist-id provided?}
    H -- yes --> I[PATCH /gists/id\nupdate existing]
    H -- no --> J[POST /gists\ncreate new]
    I --> K[Gist URL]
    J --> K
    K --> L[Job Summary\nappend dashboard]
    K --> M[Print URL to log]
```

---

### Tool Invocation Sequence

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant C as Claude API
    participant T as Tool Layer
    participant G as GitHub API
    participant V as Validation Layer

    O->>C: Send unresolved issues + tool schemas
    C->>O: Tool call: run_rule_checks(content)
    O->>T: Execute run_rule_checks
    T->>O: Issue list with details
    O->>C: Tool result: issue list
    C->>O: Tool call: check_secret_exists("NPM_TOKEN")
    O->>T: Execute check_secret_exists
    T->>G: GET /repos/.../secrets/NPM_TOKEN
    G->>T: 404 Not Found
    T->>O: {exists: false}
    O->>C: Tool result: secret not found
    C->>O: Tool call: propose_fix(issue, file_section)
    O->>T: Execute propose_fix → Claude API
    T->>O: {patch: yaml_str, confidence: 0.85}
    O->>C: Tool result: patch proposed
    C->>O: Tool call: apply_fix(path, patch)
    O->>T: Execute apply_fix in memory
    T->>O: patched content
    O->>V: Validate patched content
    V->>O: Validation passed
    O->>C: Tool result: fix validated
    C->>O: Signal: done
    O->>O: Write files + git commit + open PR
```

---

*CIRecon is open source under the MIT License. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).*
