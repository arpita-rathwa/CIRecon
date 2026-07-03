import re
from cirecon.rule_engine import Issue


def apply_fix(content: str, issue: Issue) -> str:
    if issue.id == "RULE_DEPRECATED_ACTION":
        action_name = issue.suggested_fix.rsplit("@", 1)[0]
        content = re.sub(
            rf"({re.escape(action_name)}@)[^\s\"']+",
            issue.suggested_fix,
            content
        )

    if issue.id == "RULE_MISSING_PERMISSIONS_BLOCK":
        permissions_block = "permissions:\n  contents: read\n\n"
        content = content.replace("jobs:", permissions_block + "jobs:", 1)

    return content