import re

from cirecon.rule_engine import Issue


def apply_fix(content: str, issue: Issue) -> str:
    print(f"\n--- apply_fix: {issue.id} ---")
    print(f"  suggested_fix: {issue.suggested_fix!r}")

    if issue.id == "RULE_DEPRECATED_ACTION":
        msg_match = re.search(r"'([^']+)'", issue.message)
        deprecated_str = msg_match.group(1) if msg_match else ""
        if deprecated_str:
            print(f"  replacing: {deprecated_str!r} -> {issue.suggested_fix!r}")
            content = content.replace(deprecated_str, issue.suggested_fix, 1)
        else:
            action_name = issue.suggested_fix.rsplit("@", 1)[0]
            content = re.sub(
                rf"{re.escape(action_name)}@[^\s\"']+",
                issue.suggested_fix,
                content,
                count=1,
            )

    if issue.id == "RULE_MISSING_PERMISSIONS_BLOCK":
        permissions_block = "permissions:\n  contents: read\n\n"
        content = re.sub(
            r"^(\s*)jobs:",
            r"\1" + permissions_block + r"\1" + "jobs:",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    print(f"  content after fix:\n{content}")
    return content