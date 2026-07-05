import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Location:
    file: str
    line: Optional[int]
    column: Optional[int]


@dataclass
class Issue:
    id: str
    severity: Severity
    message: str
    location: Location
    auto_fixable: bool
    confidence: float        # 0.0 to 1.0
    suggested_fix: Optional[str]


DEPRECATED_ACTIONS = {
    "actions/checkout": "v4",
    "actions/setup-python": "v5",
    "actions/setup-node": "v4",
    "actions/upload-artifact": "v4",
    "actions/download-artifact": "v4",
    "actions/cache": "v4",
}


def check_deprecated_action_versions(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed or "jobs" not in parsed:
        return issues

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses", "")
            if not uses or "@" not in uses:
                continue

            action, version = uses.rsplit("@", 1)
            if action not in DEPRECATED_ACTIONS:
                continue

            # skip SHA-pinned actions — intentional security practice
            is_sha_pin = bool(re.fullmatch(r"[0-9a-f]{40}", version))
            if is_sha_pin:
                continue

            latest = DEPRECATED_ACTIONS[action]
            major_version = version.split(".", 1)[0]
            if major_version != latest:
                issues.append(Issue(
                    id="RULE_DEPRECATED_ACTION",
                    severity=Severity.MEDIUM,
                    message=f"'{action}@{version}' is outdated. Latest is '@{latest}'.",
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=True,
                    confidence=1.0,
                    suggested_fix=f"{action}@{latest}"
                ))

    return issues


def check_missing_permissions(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed:
        return issues

    # check top-level permissions block
    if "permissions" not in parsed:
        issues.append(Issue(
            id="RULE_MISSING_PERMISSIONS_BLOCK",
            severity=Severity.HIGH,
            message="Workflow has no top-level 'permissions' block. "
                    "Without explicit permissions, the GITHUB_TOKEN has "
                    "broad default access.",
            location=Location(file=path, line=None, column=None),
            auto_fixable=True,
            confidence=0.9,
            suggested_fix="permissions:\n  contents: read"
        ))
        return issues  # no need to check jobs if top-level is missing

    return issues

def check_broken_needs_dependencies(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed:
        return issues
    
    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    valid_job_ids = set(jobs.keys())
        # e.g. {"build", "test", "deploy"}
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
    
        needs = job.get("needs")
        if not needs:
            continue  # this job has no needs, skip it
        
    # needs can be a string OR a list
        if isinstance(needs, str):
            needs = [needs]
    
        for needed_job in needs:
            if needed_job not in valid_job_ids:
                issues.append(Issue(
                    id="RULE_BROKEN_NEEDS_DEPENDENCY",
                    severity=Severity.HIGH,
                    message=f"Job '{job_name}' depends on '{needed_job}' which does not exist.",
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=False,
                    confidence=1.0,
                    suggested_fix=None
                ))
    
    return issues  # no need to check jobs if top-level is missing

def check_secret_in_run_command(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed or "jobs" not in parsed:
        return issues

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            run_cmd = step.get("run", "")
            if isinstance(run_cmd, str) and "${{ secrets." in run_cmd:
                issues.append(Issue(
                    id="RULE_SECRET_IN_RUN_COMMAND",
                    severity=Severity.CRITICAL,
                    message=f"Job '{job_name}' prints a secret to logs via run command. "
                            "Secrets in run commands are exposed in plain text in workflow logs.",
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=False,
                    confidence=0.95,
                    suggested_fix=None
                ))

    return issues

def check_pull_request_target_unsafe(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed:
        return issues

    # YAML 1.1 parses "on" as boolean True, so check both
    on_value = parsed.get("on", parsed.get(True, {}))
    if not isinstance(on_value, dict):
        if isinstance(on_value, str):
            triggers = [on_value]
        elif isinstance(on_value, list):
            triggers = on_value
        else:
            triggers = []
        has_pr_target = any(
            isinstance(t, str) and t == "pull_request_target" for t in triggers
        )
    else:
        triggers = list(on_value.keys())
        has_pr_target = "pull_request_target" in triggers

    if not has_pr_target:
        return issues

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses", "")
            if "actions/checkout" not in uses:
                continue
            with_ = step.get("with", {}) or {}
            ref = with_.get("ref", "")
            if isinstance(ref, str) and "github.event.pull_request" in ref:
                issues.append(Issue(
                    id="RULE_PULL_REQUEST_TARGET_UNSAFE",
                    severity=Severity.CRITICAL,
                    message=(
                        f"Job '{job_name}' uses pull_request_target "
                        "with checkout of untrusted PR code. "
                        "This is a known RCE vector — "
                        "pull_request_target gives write access to the repo."
                    ),
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=False,
                    confidence=0.9,
                    suggested_fix=None
                ))

    return issues


def check_overly_broad_permissions(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed:
        return issues

    perms = parsed.get("permissions", {})
    if isinstance(perms, str):
        if perms == "write-all" or perms == "write":
            issues.append(Issue(
                id="RULE_OVERLY_BROAD_PERMISSIONS",
                severity=Severity.HIGH,
                message=(
                    "Top-level permissions are set to 'write-all' or 'write', "
                    "which gives broad access to the entire repo. "
                    "Restrict to only the scopes needed (e.g. contents: read)."
                ),
                location=Location(file=path, line=None, column=None),
                auto_fixable=False,
                confidence=1.0,
                suggested_fix=None
            ))
            return issues
    elif isinstance(perms, dict):
        write_scopes = [k for k, v in perms.items() if v == "write"]
        if len(write_scopes) > 2:
            issues.append(Issue(
                id="RULE_OVERLY_BROAD_PERMISSIONS",
                severity=Severity.HIGH,
                message=(
                    f"Permissions grant write access to {len(write_scopes)} "
                    f"scopes ({', '.join(write_scopes)}). "
                    "Broad permissions increase the blast radius "
                    "if the workflow is compromised."
                ),
                location=Location(file=path, line=None, column=None),
                auto_fixable=False,
                confidence=1.0,
                suggested_fix=None
            ))

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_perms = job.get("permissions", {})
        if isinstance(job_perms, str):
            if job_perms == "write-all":
                issues.append(Issue(
                    id="RULE_OVERLY_BROAD_PERMISSIONS",
                    severity=Severity.HIGH,
                    message=(
                        f"Job '{job_name}' sets permissions to "
                        f"'{job_perms}', which is overly broad."
                    ),
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=False,
                    confidence=1.0,
                    suggested_fix=None
                ))

    return issues


def check_unpinned_third_party_action(path: str, content: str) -> list[Issue]:
    issues = []

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        return issues

    if not parsed or "jobs" not in parsed:
        return issues

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses", "")
            if not uses or "@" not in uses:
                continue

            action, version = uses.rsplit("@", 1)

            # skip GitHub-owned actions (actions/*, github/*)
            if action.startswith("actions/") or action.startswith("github/"):
                continue

            # skip SHA-pinned actions (40-char hex)
            is_sha_pin = bool(re.fullmatch(r"[0-9a-f]{40}", version))
            if is_sha_pin:
                continue

            issues.append(Issue(
                id="RULE_UNPINNED_THIRD_PARTY_ACTION",
                severity=Severity.HIGH,
                message=f"Third-party action '{uses}' is not pinned to a full commit SHA. "
                        "Unpinned actions can be silently updated with malicious code.",
                location=Location(file=path, line=None, column=None),
                auto_fixable=False,
                confidence=1.0,
                suggested_fix=None
            ))

    return issues


def run_all_checks(path, content) -> list[Issue]:
    result = (
        check_deprecated_action_versions(path, content)
        + check_broken_needs_dependencies(path, content)
        + check_missing_permissions(path, content)
        + check_secret_in_run_command(path, content)
        + check_pull_request_target_unsafe(path, content)
        + check_overly_broad_permissions(path, content)
        + check_unpinned_third_party_action(path, content)
    )
    return result
