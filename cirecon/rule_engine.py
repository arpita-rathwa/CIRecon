from dataclasses import dataclass
from typing import Optional
from enum import Enum
import re
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

def check_broken_needs_dependencies(path: str, content: str) -> list[Issue]:
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
        needs = job.get("needs")
        if needs is None:
            continue

        # needs can be a string or a list
        needed_jobs = [needs] if isinstance(needs, str) else needs

        for needed in needed_jobs:
            if needed not in jobs:
                issues.append(Issue(
                    id="RULE_BROKEN_NEEDS_DEPENDENCY",
                    severity=Severity.HIGH,
                    message=f"Job '{job_name}' references non-existent job "
                            f"'{needed}' in 'needs'.",
                    location=Location(file=path, line=None, column=None),
                    auto_fixable=False,
                    confidence=1.0,
                    suggested_fix=None
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
