from cirecon.fix_applier import apply_fix
from cirecon.rule_engine import Issue, Location, Severity
from cirecon.validator import validate_all


def test_fixes_deprecated_action():
    content = """\
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v4
"""
    issue = Issue(
        id="RULE_DEPRECATED_ACTION",
        severity=Severity.MEDIUM,
        message="'actions/checkout@v2' is outdated. Latest is '@v4'.",
        location=Location(file="test.yml", line=None, column=None),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="actions/checkout@v4",
    )
    result = apply_fix(content, issue)

    assert "actions/checkout@v4" in result
    assert "actions/checkout@v2" not in result


def test_fixes_missing_permissions():
    content = """\
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""
    issue = Issue(
        id="RULE_MISSING_PERMISSIONS_BLOCK",
        severity=Severity.HIGH,
        message="Workflow has no top-level 'permissions' block.",
        location=Location(file="test.yml", line=None, column=None),
        auto_fixable=True,
        confidence=0.9,
        suggested_fix="permissions:\n  contents: read",
    )
    result = apply_fix(content, issue)

    assert "permissions:" in result


def test_deprecated_action_validate_all():
    content = """\
name: CI
'on': [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
"""
    issue = Issue(
        id="RULE_DEPRECATED_ACTION",
        severity=Severity.MEDIUM,
        message="'actions/checkout@v2' is outdated. Latest is '@v4'.",
        location=Location(file="test.yml", line=None, column=None),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="actions/checkout@v4",
    )
    result = apply_fix(content, issue)
    validation = validate_all("test.yml", result, [issue])
    assert validation.passed is True, f"Validation failed: {validation.errors}"


def test_missing_permissions_validate_all():
    content = """\
name: CI
'on': [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""
    issue = Issue(
        id="RULE_MISSING_PERMISSIONS_BLOCK",
        severity=Severity.HIGH,
        message="Workflow has no top-level 'permissions' block.",
        location=Location(file="test.yml", line=None, column=None),
        auto_fixable=True,
        confidence=0.9,
        suggested_fix="permissions:\n  contents: read",
    )
    result = apply_fix(content, issue)
    validation = validate_all("test.yml", result, [issue])
    assert validation.passed is True, f"Validation failed: {validation.errors}"


def test_fixes_deprecated_action_regex_fallback():
    content = """\
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
"""
    issue = Issue(
        id="RULE_DEPRECATED_ACTION",
        severity=Severity.MEDIUM,
        message="Unrecognized deprecated action reference",
        location=Location(file="test.yml", line=None, column=None),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="actions/checkout@v4",
    )
    result = apply_fix(content, issue)
    assert "actions/checkout@v4" in result
    assert "actions/checkout@v2" not in result
