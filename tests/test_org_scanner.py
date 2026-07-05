from unittest.mock import patch

from cirecon.org_scanner import _calculate_health_score, scan_repos
from cirecon.rule_engine import Issue, Location, Severity


def test_calculate_health_score_clean():
    score = _calculate_health_score([])
    assert score == 100


def test_calculate_health_score_critical():
    issues = [
        Issue(id="R1", severity=Severity.CRITICAL, message="x",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
    ]
    score = _calculate_health_score(issues)
    assert score == 80


def test_calculate_health_score_mixed():
    issues = [
        Issue(id="R1", severity=Severity.CRITICAL, message="x",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
        Issue(id="R2", severity=Severity.HIGH, message="y",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
        Issue(id="R3", severity=Severity.MEDIUM, message="z",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
        Issue(id="R4", severity=Severity.LOW, message="w",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None),
    ]
    score = _calculate_health_score(issues)
    assert score == 100 - 20 - 10 - 5 - 2


def test_calculate_health_score_minimum_zero():
    issues = [
        Issue(id=f"R{i}", severity=Severity.CRITICAL, message="x",
              location=Location(file="f.yml", line=None, column=None),
              auto_fixable=False, confidence=1.0, suggested_fix=None)
        for i in range(10)
    ]
    score = _calculate_health_score(issues)
    assert score == 0


@patch("cirecon.org_scanner.subprocess.run")
@patch("cirecon.org_scanner.discover_workflow_files")
@patch("cirecon.org_scanner.run_all_checks")
def test_scan_repos_success(mock_checks, mock_discover, mock_run):
    mock_discover.return_value = [("ci.yml", "name: CI")]
    mock_checks.return_value = [
        Issue(id="RULE_DEPRECATED_ACTION", severity=Severity.MEDIUM, message="old",
              location=Location(file="ci.yml", line=None, column=None),
              auto_fixable=True, confidence=1.0, suggested_fix="actions/checkout@v4"),
    ]

    reports = scan_repos(["owner/repo1"], "ghp_token")
    assert len(reports) == 1
    assert reports[0].repo == "owner/repo1"
    assert reports[0].files_scanned == 1
    assert reports[0].health_score == 95
    assert len(reports[0].issues) == 1
    assert "UTC" in reports[0].scanned_at
