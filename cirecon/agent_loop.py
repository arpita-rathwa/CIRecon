import json
from dataclasses import dataclass, field
from typing import Optional

import requests

from cirecon.memory import MemoryContext
from cirecon.tools import (
    apply_fix_tool,
    check_secret_exists,
    create_branch_and_pr,
    propose_fix,
    read_workflow_file,
    run_rule_checks_tool,
    validate_yaml_schema_tool,
)
from cirecon.validator import ValidationResult

CLAUDE_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class AgentState:
    scanned_files: list[str] = field(default_factory=list)
    issues_found: list[dict] = field(default_factory=list)
    issues_fixed: list[dict] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    iteration: int = 0
    tool_history: list[dict] = field(default_factory=list)
    patches: list[dict] = field(default_factory=list)
    applied_fixes: list[dict] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)


TOOL_DEFINITIONS = [
    {
        "name": "read_workflow_file",
        "description": "Read a workflow YAML file from disk and return its contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the workflow file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "validate_yaml_schema",
        "description": "Validate YAML content against the GitHub Actions workflow schema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "YAML content to validate",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "run_rule_checks",
        "description": "Run all rule engine checks on the given workflow content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path for location context"},
                "content": {
                    "type": "string",
                    "description": "YAML workflow content to check",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "check_secret_exists",
        "description": "Check if a named secret exists in the GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "secret_name": {
                    "type": "string",
                    "description": "Name of the secret to check",
                },
            },
            "required": ["secret_name"],
        },
    },
    {
        "name": "propose_fix",
        "description": "Ask Claude to generate a YAML fix for a given issue and file section.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "ID of the issue to fix",
                },
                "file_section": {
                    "type": "string",
                    "description": "Relevant YAML section from the workflow file",
                },
            },
            "required": ["issue_id", "file_section"],
        },
    },
    {
        "name": "apply_fix",
        "description": "Apply a proposed YAML patch to a workflow file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to patch"},
                "patch": {
                    "type": "string",
                    "description": "The fixed YAML content to apply",
                },
            },
            "required": ["path", "patch"],
        },
    },
    {
        "name": "create_pr",
        "description": "Create a pull request with all accumulated patches. Call this when all fixes are applied.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def build_context(state: AgentState, memory: MemoryContext) -> list[dict]:
    unresolved_text = ""
    if state.unresolved:
        lines = []
        for i, issue in enumerate(state.unresolved):
            lines.append(
                f"{i+1}. [{issue.get('id', '?')}] {issue.get('message', '')} "
                f"(file: {issue.get('location', {}).get('file', '?')}, "
                f"auto_fixable: {issue.get('auto_fixable', False)})"
            )
        unresolved_text = "\n".join(lines)
    else:
        unresolved_text = "No issues remaining."

    rejected_text = ""
    if memory.rejected_fixes:
        rejected_text = "Previously rejected fixes (do not retry): " + ", ".join(
            memory.rejected_fixes
        )

    known_secrets_text = ""
    if memory.known_secrets:
        known_secrets_text = (
            "Known repository secrets: " + ", ".join(memory.known_secrets)
        )

    system_prompt = (
        "You are CIRecon, an AI assistant that repairs GitHub Actions workflow files. "
        "Your job is to fix issues found by the rule engine.\n\n"
        "Available tools:\n"
        "- read_workflow_file: Read a workflow file from disk\n"
        "- validate_yaml_schema: Validate YAML against the GitHub Actions schema\n"
        "- run_rule_checks: Run rule engine checks on content\n"
        "- check_secret_exists: Check if a GitHub secret exists\n"
        "- propose_fix: Generate a YAML fix for an issue\n"
        "- apply_fix: Apply a patch to a file\n"
        "- create_pr: Create a pull request with all fixes\n\n"
        "Rules:\n"
        "1. First read the affected file with read_workflow_file\n"
        "2. For each issue, call propose_fix then apply_fix\n"
        "3. After each fix, validate with run_rule_checks\n"
        "4. When all issues are resolved, call create_pr\n"
        "5. If an issue is not auto_fixable, skip it and move on\n"
        "6. Do NOT retry fixes that are in the rejected list\n"
        "7. Do NOT call the same tool with the same arguments twice"
    )

    user_message = (
        f"## Current State\n\n"
        f"Iteration: {state.iteration + 1}\n\n"
        f"### Unresolved Issues\n{unresolved_text}\n\n"
        f"### Already Fixed ({len(state.issues_fixed)})\n"
    )
    if state.issues_fixed:
        for fix in state.issues_fixed:
            user_message += f"- {fix.get('id', '?')}: {fix.get('message', '')}\n"
    else:
        user_message += "None yet.\n"

    if rejected_text:
        user_message += f"\n### {rejected_text}\n"
    if known_secrets_text:
        user_message += f"\n### {known_secrets_text}\n"

    user_message += "\nContinue fixing the remaining issues or call create_pr if done."

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]


def dispatch_tool(tool_name: str, tool_input: dict, context: dict) -> dict:
    try:
        if tool_name == "read_workflow_file":
            result = read_workflow_file(tool_input["path"])
        elif tool_name == "validate_yaml_schema":
            result = validate_yaml_schema_tool(tool_input["content"])
        elif tool_name == "run_rule_checks":
            result = run_rule_checks_tool(
                tool_input["path"], tool_input["content"]
            )
        elif tool_name == "check_secret_exists":
            result = check_secret_exists(
                tool_input["secret_name"],
                context["github_token"],
                context["repo"],
            )
        elif tool_name == "propose_fix":
            issue_id = tool_input["issue_id"]
            issue_dict = _find_issue_by_id(context["state"], issue_id)
            result = propose_fix(
                issue_dict,
                tool_input["file_section"],
                context["api_key"],
            )
        elif tool_name == "apply_fix":
            result = apply_fix_tool(tool_input["path"], tool_input["patch"])
        elif tool_name == "create_pr":
            result = create_branch_and_pr(
                context["state"].applied_fixes,
                context["state"].issues_fixed,
                context["state"].unresolved,
                context["github_token"],
                context["repo"],
            )
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _find_issue_by_id(state: AgentState, issue_id: str) -> dict:
    for issue in state.unresolved:
        if issue.get("id") == issue_id:
            return issue
    for issue in state.issues_found:
        if issue.get("id") == issue_id:
            return issue
    return {"id": issue_id, "message": issue_id}


def _call_claude(
    messages: list[dict], api_key: str
) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4000,
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _update_state_from_dispatch(
    state: AgentState, tool_name: str, tool_input: dict, result: dict
) -> None:
    if not result.get("success"):
        return

    if tool_name == "read_workflow_file":
        path = result["data"].get("path", tool_input.get("path", ""))
        if path and path not in state.scanned_files:
            state.scanned_files.append(path)

    elif tool_name == "propose_fix":
        patch = result["data"].get("patch", "")
        issue_id = tool_input.get("issue_id", "unknown")
        state.patches.append(
            {"issue_id": issue_id, "patch": patch, "file_section": tool_input.get("file_section", "")}
        )

    elif tool_name == "apply_fix":
        path = tool_input.get("path", "")
        patch = tool_input.get("patch", "")
        issue_id = ""
        for p in state.patches:
            if p.get("patch") == patch:
                issue_id = p.get("issue_id", "")
                break
        fixed_issue = None
        for i, issue in enumerate(state.unresolved):
            if issue.get("id") == issue_id:
                fixed_issue = state.unresolved.pop(i)
                break
        if fixed_issue:
            state.issues_fixed.append(fixed_issue)
            state.applied_fixes.append({"path": path, "content": patch})


def run_agent_loop(
    unresolved: list[dict],
    memory: MemoryContext,
    api_key: str,
    max_iterations: int = 10,
    repo: str = "",
    github_token: str = "",
) -> AgentState:
    state = AgentState(unresolved=unresolved, issues_found=list(unresolved))
    seen_calls: set[tuple[str, str]] = set()
    context = {
        "api_key": api_key,
        "github_token": github_token,
        "repo": repo,
        "state": state,
    }

    for iteration in range(max_iterations):
        state.iteration = iteration

        if not state.unresolved:
            break

        messages = build_context(state, memory)
        try:
            response = _call_claude(messages, api_key)
        except requests.RequestException as e:
            state.tool_history.append(
                {"error": f"Claude API call failed: {e}"}
            )
            break

        content_blocks = response.get("content", [])
        tool_calls = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_calls:
            text_blocks = [
                b for b in content_blocks if b.get("type") == "text"
            ]
            if text_blocks:
                state.tool_history.append(
                    {"claude_text": text_blocks[0].get("text", "")}
                )
            break

        for block in tool_calls:
            tool_name = block["name"]
            tool_input = block.get("input", {})
            call_id = block["id"]
            call_key = (tool_name, json.dumps(tool_input, sort_keys=True))

            if call_key in seen_calls:
                state.tool_history.append(
                    {
                        "warning": f"Infinite loop guard: skipping duplicate call to {tool_name}",
                        "call_id": call_id,
                    }
                )
                continue
            seen_calls.add(call_key)

            result = dispatch_tool(tool_name, tool_input, context)
            _update_state_from_dispatch(state, tool_name, tool_input, result)

            state.tool_history.append(
                {
                    "call_id": call_id,
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result,
                }
            )

    return state
