from unittest.mock import patch

from cirecon.rule_engine import Issue, Location, Severity
from cirecon.validator import (
    validate_all,
    validate_rule_recheck,
    validate_schema,
    validate_yaml_syntax,
)

MINIMAL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "on": {},
        "permissions": {
            "type": "object",
            "properties": {"contents": {"type": "string"}},
        },
        "jobs": {
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "properties": {
                        "runs-on": {"type": "string"},
                        "steps": {"type": "array"},
                    },
                }
            },
        },
    },
    "required": ["on", "jobs"],
}


def test_valid_yaml_passes():
    content = "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest"
    result = validate_yaml_syntax(content)
    assert result.passed is True
    assert result.errors == []


def test_broken_yaml_fails():
    content = "name: CI\non: [push\njobs:\n  build:\n    runs-on: ubuntu-latest"
    result = validate_yaml_syntax(content)
    assert result.passed is False
    assert len(result.errors) > 0


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_schema_valid_workflow_passes():
    content = (
        "name: CI\n'on': [push]\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n"
    )
    result = validate_schema(content)
    assert result.passed is True
    assert result.errors == []


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_schema_missing_on_fails():
    content = (
        "name: CI\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n"
    )
    result = validate_schema(content)
    assert result.passed is False
    assert len(result.errors) > 0


def test_rule_recheck_no_new_issues():
    content = (
        "name: CI\non: [push]\npermissions:\n  contents: read\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n"
    )
    issues = [
        Issue(
            id="RULE_DEPRECATED_ACTION",
            severity=Severity.MEDIUM,
            message="",
            location=Location(file="f.yml", line=None, column=None),
            auto_fixable=True,
            confidence=1.0,
            suggested_fix="actions/checkout@v4",
        )
    ]
    result = validate_rule_recheck("f.yml", content, issues)
    assert result.passed is True


def test_rule_recheck_new_issue_introduced():
    content = (
        "name: CI\non: [push]\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n"
    )
    result = validate_rule_recheck("f.yml", content, [])
    assert result.passed is False
    assert any("permissions" in e for e in result.errors)


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_validate_all_good_fix_passes():
    content = (
        "name: CI\n'on': [push]\npermissions:\n  contents: read\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n"
    )
    issues = [
        Issue(
            id="RULE_DEPRECATED_ACTION",
            severity=Severity.MEDIUM,
            message="",
            location=Location(file="f.yml", line=None, column=None),
            auto_fixable=True,
            confidence=1.0,
            suggested_fix="actions/checkout@v4",
        )
    ]
    result = validate_all("f.yml", content, issues)
    assert result.passed is True


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_validate_all_broken_fix_fails():
    content = "this is not: yaml\n  - broken"
    issues = []
    result = validate_all("f.yml", content, issues)
    assert result.passed is False


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_validate_schema_empty_content():
    result = validate_schema("")
    assert result.passed is False
    assert "Empty YAML content" in " ".join(result.errors)


@patch("cirecon.validator.fetch_github_actions_schema")
def test_validate_schema_network_error(mock_fetch):
    from requests import RequestException
    mock_fetch.side_effect = RequestException("Network failure")
    result = validate_schema("name: CI\non: [push]\n")
    assert result.passed is False
    assert "Schema fetch error" in " ".join(result.errors)
