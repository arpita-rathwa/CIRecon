import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import jsonschema
import requests
import yaml

from cirecon.rule_engine import run_all_checks

_SCHEMA_CACHE: Optional[dict] = None


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str]


def validate_yaml_syntax(content: str) -> ValidationResult:
    try:
        yaml.safe_load(content)
        return ValidationResult(passed=True, errors=[])
    except yaml.YAMLError as e:
        return ValidationResult(passed=False, errors=[str(e)])


def fetch_github_actions_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE
    try:
        resp = requests.get("https://json.schemastore.org/github-workflow.json", timeout=30)
        resp.raise_for_status()
        _SCHEMA_CACHE = resp.json()
        return _SCHEMA_CACHE
    except requests.RequestException:
        schema_path = Path(__file__).parent / "schemas" / "github-workflow.json"
        with open(schema_path, encoding="utf-8") as f:
            _SCHEMA_CACHE = json.load(f)
        return _SCHEMA_CACHE


def validate_schema(content: str) -> ValidationResult:
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return ValidationResult(passed=False, errors=[f"YAML parse error: {e}"])
    if parsed is None:
        return ValidationResult(passed=False, errors=["Empty YAML content"])
    try:
        schema = fetch_github_actions_schema()
        jsonschema.validate(parsed, schema)
        return ValidationResult(passed=True, errors=[])
    except jsonschema.ValidationError as e:
        if "not allowed" in e.message and "unexpected" in e.message:
            return ValidationResult(passed=True, errors=[])
        return ValidationResult(passed=False, errors=[e.message])
    except requests.RequestException as e:
        return ValidationResult(passed=False, errors=[f"Schema fetch error: {e}"])


def validate_rule_recheck(path: str, content: str, original_issues: list) -> ValidationResult:
    original_keys = {(i.id, i.location.file) for i in original_issues}
    new_issues = run_all_checks(path, content)
    new_keys = {(i.id, i.location.file) for i in new_issues}
    introduced = new_keys - original_keys
    if introduced:
        details = [i.message for i in new_issues if (i.id, i.location.file) in introduced]
        return ValidationResult(passed=False, errors=details)
    return ValidationResult(passed=True, errors=[])


def validate_all(path: str, content: str, original_issues: list) -> ValidationResult:
    syntax_result = validate_yaml_syntax(content)
    if not syntax_result.passed:
        return syntax_result
    schema_result = validate_schema(content)
    if not schema_result.passed:
        return schema_result
    return validate_rule_recheck(path, content, original_issues)