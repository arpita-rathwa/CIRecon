from cirecon.rule_engine import (
    check_broken_needs_dependencies,
    check_deprecated_action_versions,
    check_missing_permissions,
    check_overly_broad_permissions,
    check_pull_request_target_unsafe,
    check_secret_in_run_command,
    check_unpinned_third_party_action,
    run_all_checks,
)


def load_fixture(filename: str) -> str:
    with open(f"tests/fixtures/{filename}", "r", encoding="utf-8") as f:
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

def test_run_all_checks_combines_results():
    content = load_fixture("deprecated_action.yml")
    issues = run_all_checks("deprecated_action.yml", content)

    ids = [i.id for i in issues]

    # deprecated_action.yml has outdated actions AND no permissions block
    assert "RULE_DEPRECATED_ACTION" in ids
    assert "RULE_MISSING_PERMISSIONS_BLOCK" in ids


def test_detects_secret_in_run_command():
    content = load_fixture("secret_in_run.yml")
    issues = check_secret_in_run_command("secret_in_run.yml", content)
    assert len(issues) >= 1
    assert issues[0].id == "RULE_SECRET_IN_RUN_COMMAND"
    assert issues[0].severity.value == "critical"


def test_no_secret_issue_on_clean_file():
    content = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "hello"
      - uses: actions/checkout@v4
"""
    issues = check_secret_in_run_command("clean.yml", content)
    assert len(issues) == 0


def test_detects_pull_request_target_unsafe():
    content = load_fixture("pull_request_target_unsafe.yml")
    issues = check_pull_request_target_unsafe("pull_request_target_unsafe.yml", content)
    assert len(issues) >= 1
    assert issues[0].id == "RULE_PULL_REQUEST_TARGET_UNSAFE"
    assert "RCE" in issues[0].message


def test_no_pull_request_target_issue_on_clean_file():
    content = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
    issues = check_pull_request_target_unsafe("clean.yml", content)
    assert len(issues) == 0


def test_detects_overly_broad_permissions():
    content = load_fixture("overly_broad_permissions.yml")
    issues = check_overly_broad_permissions("overly_broad_permissions.yml", content)
    assert len(issues) >= 1
    assert issues[0].id == "RULE_OVERLY_BROAD_PERMISSIONS"


def test_no_overly_broad_permissions_on_clean_file():
    content = """
name: CI
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "hello"
"""
    issues = check_overly_broad_permissions("clean.yml", content)
    assert len(issues) == 0


def test_detects_unpinned_third_party_action():
    content = load_fixture("unpinned_third_party.yml")
    issues = check_unpinned_third_party_action("unpinned_third_party.yml", content)
    assert len(issues) >= 2
    assert all(i.id == "RULE_UNPINNED_THIRD_PARTY_ACTION" for i in issues)


def test_no_unpinned_issue_on_sha_pinned():
    content = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
      - uses: some-org/safe-action@a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2
"""
    issues = check_unpinned_third_party_action("clean.yml", content)
    assert len(issues) == 0


def test_checks_return_empty_on_bad_yaml():
    bad_yaml = "name: CI\non: [push\njobs:\n  build:\n    runs-on: ubuntu-latest"
    for check in [
        check_deprecated_action_versions,
        check_missing_permissions,
        check_broken_needs_dependencies,
        check_secret_in_run_command,
        check_pull_request_target_unsafe,
        check_overly_broad_permissions,
        check_unpinned_third_party_action,
    ]:
        assert check("f.yml", bad_yaml) == []


def test_checks_return_empty_on_null_yaml():
    for check in [
        check_deprecated_action_versions,
        check_missing_permissions,
        check_pull_request_target_unsafe,
        check_overly_broad_permissions,
    ]:
        assert check("f.yml", "null") == []


def test_deprecated_action_skips_non_dict_jobs():
    content = "name: CI\non: [push]\njobs: string_value\n"
    issues = check_deprecated_action_versions("f.yml", content)
    assert issues == []


def test_secret_in_run_no_jobs():
    content = "name: CI\non: [push]\n"
    issues = check_secret_in_run_command("f.yml", content)
    assert issues == []


def test_pull_request_target_no_on_block():
    content = "name: CI\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
    issues = check_pull_request_target_unsafe("f.yml", content)
    assert issues == []


def test_overly_broad_permissions_non_dict_jobs():
    content = "name: CI\non: [push]\npermissions: write-all\njobs: string\n"
    issues = check_overly_broad_permissions("f.yml", content)
    assert len(issues) == 1
    assert issues[0].id == "RULE_OVERLY_BROAD_PERMISSIONS"