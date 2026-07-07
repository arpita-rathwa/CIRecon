import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from cirecon.main import _issue_to_dict, run, to_sarif, write_job_summary
from cirecon.memory import MemoryContext
from cirecon.rule_engine import Issue, Location, Severity


def test_issue_to_dict():
    issue = Issue(
        id="RULE_TEST",
        severity=Severity.HIGH,
        message="Test issue",
        location=Location(file="f.yml", line=5, column=2),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="fix",
    )
    d = _issue_to_dict(issue)
    assert d["id"] == "RULE_TEST"
    assert d["severity"] == "high"
    assert d["auto_fixable"] is True
    assert d["location"]["file"] == "f.yml"


@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.run_all_checks")
def test_run_no_issues_found(mock_checks, mock_discover):
    mock_discover.return_value = [("test.yml", "name: CI")]
    mock_checks.return_value = []

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0


@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.run_all_checks")
@patch("cirecon.main.apply_fix")
@patch("cirecon.main.validate_all")
def test_run_auto_fix_applied(mock_validate, mock_apply, mock_checks, mock_discover):
    mock_discover.return_value = [
        ("test.yml", "name: CI\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v2\n"),
    ]
    mock_checks.return_value = [
        Issue(
            id="RULE_DEPRECATED_ACTION",
            severity=Severity.MEDIUM,
            message="'actions/checkout@v2' is outdated",
            location=Location(file="test.yml", line=None, column=None),
            auto_fixable=True,
            confidence=1.0,
            suggested_fix="actions/checkout@v4",
        )
    ]
    mock_apply.return_value = (
        "name: CI\njobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"
    )

    valid_result = MagicMock()
    valid_result.passed = True
    valid_result.errors = []
    mock_validate.return_value = valid_result

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0


@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.run_all_checks")
@patch("cirecon.main.apply_fix")
@patch("cirecon.main.validate_all")
def test_run_auto_fix_fails_validation(mock_validate, mock_apply, mock_checks, mock_discover):
    mock_discover.return_value = [("test.yml", "bad yaml")]
    mock_checks.return_value = [
        Issue(
            id="RULE_MISSING_PERMISSIONS_BLOCK",
            severity=Severity.HIGH,
            message="Missing permissions",
            location=Location(file="test.yml", line=None, column=None),
            auto_fixable=True,
            confidence=0.9,
            suggested_fix="permissions:\n  contents: read",
        )
    ]
    mock_apply.return_value = "still bad"

    failed_result = MagicMock()
    failed_result.passed = False
    failed_result.errors = ["validation failed"]
    mock_validate.return_value = failed_result

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0


@patch("cirecon.main.discover_workflow_files")
def test_no_workflow_files(mock_discover):
    mock_discover.return_value = []
    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0


def test_write_job_summary_with_issues():
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = os.path.join(tmp, "summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            files_scanned = [("a.yml", "content"), ("b.yml", "content")]
            issues_found = [
                Issue(
                    id="RULE_A", severity=Severity.HIGH,
                    message="Missing permissions",
                    location=Location(file="a.yml", line=None, column=None),
                    auto_fixable=True, confidence=1.0,
                    suggested_fix="permissions:\n  contents: read",
                ),
                Issue(id="RULE_B", severity=Severity.CRITICAL, message="Secret in run",
                      location=Location(file="b.yml", line=None, column=None),
                      auto_fixable=False, confidence=0.95, suggested_fix=None),
            ]
            issues_fixed = [{"id": "RULE_A", "message": "Fixed"}]
            unresolved = [{"id": "RULE_B", "message": "Cannot fix"}]

            write_job_summary(files_scanned, issues_found, issues_fixed, unresolved)

            with open(summary_path, encoding="utf-8") as f:
                content = f.read()

        assert "## CIRecon Report" in content
        assert "**Files scanned:** 2" in content
        assert "**Issues found:** 2" in content
        assert "**Auto-fixable:** 1" in content
        assert "**Needs attention:** 1" in content
        assert "RULE_A" in content
        assert "RULE_B" in content
        assert "\u2705" in content
        assert "\u274c" in content
        assert "Manual fix required" in content


def test_write_job_summary_no_issues():
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = os.path.join(tmp, "summary.md")
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            write_job_summary([], [], [], [])
            with open(summary_path, encoding="utf-8") as f:
                content = f.read()

        assert "\u2705 All workflows are clean" in content
        assert "No issues detected" in content


@patch("cirecon.main.load_memory")
@patch("cirecon.main.run_all_checks")
@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.was_issue_recently_fixed")
@patch("cirecon.main.get_recurring_issues")
def test_main_skips_recently_fixed_issues(
    mock_recurring, mock_recently_fixed, mock_discover, mock_checks, mock_load
):
    mock_discover.return_value = [("test.yml", "name: CI")]
    mock_checks.return_value = [
        Issue(id="R1", severity=Severity.MEDIUM, message="old action",
              location=Location(file="test.yml", line=5, column=None),
              auto_fixable=True, confidence=1.0, suggested_fix="fix"),
    ]
    mock_load.return_value = MemoryContext(repo="test")
    mock_recurring.return_value = []
    mock_recently_fixed.return_value = True

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0


@patch("cirecon.main.load_memory")
@patch("cirecon.main.run_all_checks")
@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.was_issue_recently_fixed")
@patch("cirecon.main.get_recurring_issues")
def test_main_escalates_recurring_issues(
    mock_recurring, mock_recently_fixed, mock_discover, mock_checks, mock_load
):
    issue = Issue(id="R1", severity=Severity.MEDIUM, message="old action",
                  location=Location(file="test.yml", line=5, column=None),
                  auto_fixable=True, confidence=1.0, suggested_fix="fix")
    mock_discover.return_value = [("test.yml", "name: CI")]
    mock_checks.return_value = [issue]
    mock_load.return_value = MemoryContext(repo="test")
    mock_recurring.return_value = ["R1"]
    mock_recently_fixed.return_value = False

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0
    assert issue.severity == Severity.HIGH
    assert "RECURRING" in issue.message


def test_to_sarif_empty_issues():
    sarif = to_sarif([])
    assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"] == []


def test_to_sarif_single_issue():
    issues = [
        Issue(id="RULE_TEST", severity=Severity.CRITICAL, message="test",
              location=Location(file="f.yml", line=10, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
    ]
    sarif = to_sarif(issues)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "RULE_TEST"
    assert results[0]["level"] == "error"
    assert results[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 10


def test_to_sarif_deduplicates_rules():
    issues = [
        Issue(id="RULE_A", severity=Severity.HIGH, message="msg1",
              location=Location(file="a.yml", line=1, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
        Issue(id="RULE_A", severity=Severity.HIGH, message="msg2",
              location=Location(file="b.yml", line=2, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
    ]
    sarif = to_sarif(issues)
    assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 1


def test_to_sarif_medium_issue_is_warning():
    issues = [
        Issue(id="RULE_MED", severity=Severity.MEDIUM, message="medium",
              location=Location(file="m.yml", line=1, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
    ]
    sarif = to_sarif(issues)
    assert sarif["runs"][0]["results"][0]["level"] == "warning"


@patch("cirecon.main.load_memory")
@patch("cirecon.main.run_all_checks")
@patch("cirecon.main.discover_workflow_files")
@patch("cirecon.main.was_issue_recently_fixed")
@patch("cirecon.main.get_recurring_issues")
def test_run_writes_sarif_file(
    mock_recurring, mock_recently_fixed, mock_discover, mock_checks, mock_load
):
    mock_discover.return_value = [("test.yml", "name: CI")]
    mock_checks.return_value = [
        Issue(id="RULE_TEST", severity=Severity.HIGH, message="test",
              location=Location(file="test.yml", line=5, column=None),
              auto_fixable=True, confidence=1.0, suggested_fix="fix"),
    ]
    mock_load.return_value = MemoryContext(repo="test")
    mock_recurring.return_value = []
    mock_recently_fixed.return_value = False

    sarif_path = os.path.join(os.getenv("GITHUB_WORKSPACE", "."), "cirecon-results.sarif")
    if os.path.exists(sarif_path):
        os.unlink(sarif_path)

    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 0

    assert os.path.exists(sarif_path), "SARIF file was not written"
    with open(sarif_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == "2.1.0"
    assert len(data["runs"][0]["results"]) == 1

    if os.path.exists(sarif_path):
        os.unlink(sarif_path)


def test_write_job_summary_no_env_var():
    with patch.dict(os.environ, {}, clear=True):
        write_job_summary([], [], [], [])
    # no crash = pass
