import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from cirecon.tools import (
    apply_fix_tool,
    check_secret_exists,
    propose_fix,
    read_workflow_file,
    run_rule_checks_tool,
    validate_yaml_schema_tool,
)

MINIMAL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "on": {},
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


def test_read_workflow_file_success():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.yml"
        f.write_text("name: CI\non: [push]\n", encoding="utf-8")
        result = read_workflow_file(str(f))
        assert result.success is True
        assert "name: CI" in result.data["content"]


def test_read_workflow_file_not_found():
    result = read_workflow_file("nonexistent.yml")
    assert result.success is False
    assert result.error is not None


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_validate_yaml_schema_tool_passes():
    content = (
        "name: CI\n'on': [push]\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n"
    )
    result = validate_yaml_schema_tool(content)
    assert result.success is True
    assert result.data["passed"] is True


@patch("cirecon.validator._SCHEMA_CACHE", MINIMAL_SCHEMA)
def test_validate_yaml_schema_tool_fails():
    content = "name: CI\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
    result = validate_yaml_schema_tool(content)
    assert result.success is False
    assert result.error is not None


def test_run_rule_checks_tool_finds_issues():
    content = (
        "name: CI\non: [push]\n"
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v2\n"
    )
    result = run_rule_checks_tool("test.yml", content)
    assert result.success is True
    assert result.data["count"] >= 1
    ids = [i["id"] for i in result.data["issues"]]
    assert "RULE_DEPRECATED_ACTION" in ids


@patch("cirecon.tools.requests.get")
def test_check_secret_exists_found(mock_get):
    mock_get.return_value.status_code = 200
    result = check_secret_exists("MY_SECRET", "ghp_token", "test/repo")
    assert result.success is True
    assert result.data["exists"] is True
    mock_get.assert_called_once()


@patch("cirecon.tools.requests.get")
def test_check_secret_exists_not_found(mock_get):
    mock_get.return_value.status_code = 404
    result = check_secret_exists("NONEXISTENT", "ghp_token", "test/repo")
    assert result.success is True
    assert result.data["exists"] is False


@patch("cirecon.tools.requests.post")
def test_propose_fix_returns_patch(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "content": [{"text": "jobs:\n  build:\n    runs-on: ubuntu-latest"}]
    }
    issue = {"message": "Deprecated action"}
    result = propose_fix(issue, "some yaml", "sk-ant-api-key")
    assert result.success is True
    assert "jobs:" in result.data["patch"]
    assert result.data["confidence"] == 0.85
    mock_post.assert_called_once()


@patch("cirecon.tools.requests.post")
def test_propose_fix_api_error(mock_post):
    mock_post.side_effect = requests.RequestException("API error")
    issue = {"message": "Deprecated action"}
    result = propose_fix(issue, "some yaml", "sk-ant-api-key")
    assert result.success is False
    assert result.error is not None


def test_apply_fix_tool_success():
    patch = "name: CI\non: [push]\npermissions:\n  contents: read\n"
    result = apply_fix_tool("test.yml", patch)
    assert result.success is True
    assert result.data["patched"] == patch
    assert result.data["path"] == "test.yml"


def test_apply_fix_tool_file_not_found():
    result = apply_fix_tool("nonexistent.yml", "patch")
    assert result.success is True
    assert result.data["patched"] == "patch"

