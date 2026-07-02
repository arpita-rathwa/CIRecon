from dataclasses import dataclass
from typing import Optional
from enum import Enum


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

import re
import yaml


# Deprecated action versions that should be bumped
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
        return issues  # syntax errors handled by a separate rule

    if not parsed or "jobs" not in parsed:
        return issues

    jobs = parsed.get("jobs")
    if not isinstance(jobs, dict):
        return issues

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            action, version = uses.rsplit("@", 1)

            if action in DEPRECATED_ACTIONS:
                latest = DEPRECATED_ACTIONS[action]
                is_sha_pin = bool(re.fullmatch(r"[0-9a-f]{40}", version))
                major_version = version.split(".", 1)[0]
                if not is_sha_pin and major_version != latest:
                    issues.append(Issue(
                        id="RULE_DEPRECATED_ACTION",
                        severity=Severity.MEDIUM,
                        message=f"'{action}@{version}' is outdated. Latest is '@{latest}'.",
                        location=Location(file=path, line=None, column=None),
                        auto_fixable=True,
                        confidence=1.0,
                        suggested_fix=f"{action}@{latest}"
                    ))                        id="RULE_DEPRECATED_ACTION",
                        severity=Severity.MEDIUM,
                        message=f"'{action}@{version}' is outdated. Latest is '@{latest}'.",
                        location=Location(file=path, line=None, column=None),
                        auto_fixable=True,
                        confidence=1.0,
                        suggested_fix=f"{action}@{latest}"
                    ))

    return issues