import pytest
from cirecon.rule_engine import (
    check_deprecated_action_versions,
    check_missing_permissions,
    check_broken_needs_dependencies,
    Severity
)


def load_fixture(filename: str) -> str:
    with open(f"tests/fixtures/{filename}", "r") as f:
        return f.read()


def test_detects_deprecated_action_versions():
    content = load_fixture("deprecated_action.yml")
    issues = check_deprecated_action_versions("deprecated_action.yml", content)

    assert len(issues) == 2

    ids = [i.id for i in issues]
    assert ids.count("RULE_DEPRECATED_ACTION") == 2

    fixes = [i.suggested_fix for i in issues]
    assert "actions/checkout@v4" in fixes
    assert "actions/setup-python@v5" in fixes


def test_no_issues_on_clean_file():
    content = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
"""
    issues = check_deprecated_action_versions("clean.yml", content)
    assert len(issues) == 0



def test_detects_missing_top_level_permissions():
    content = load_fixture("missing_permissions.yml")
    issues = check_missing_permissions("missing_permissions.yml", content)

    assert len(issues) >= 1
    ids = [i.id for i in issues]
    assert "RULE_MISSING_PERMISSIONS_BLOCK" in ids


def test_no_permissions_issue_when_present():
    content = """
name: CI
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
    issues = check_missing_permissions("clean.yml", content)
    assert len(issues) == 0    


def test_detects_broken_needs_dependency():
    content = load_fixture("broken_needs.yml")
    issues = check_broken_needs_dependencies("broken_needs.yml", content)

    assert len(issues) >= 1
    ids = [i.id for i in issues]
    assert "RULE_BROKEN_NEEDS_DEPENDENCY" in ids


def test_no_needs_issue_on_clean_file():
    content = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "building"

  deploy:
    runs-on: ubuntu-latest
    needs: [build]
    steps:
      - run: echo "deploying"
"""
    issues = check_broken_needs_dependencies("clean.yml", content)
    assert len(issues) == 0   