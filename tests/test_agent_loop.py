from unittest.mock import patch

from cirecon.agent_loop import (
    TOOL_DEFINITIONS,
    AgentState,
    build_context,
    dispatch_tool,
    run_agent_loop,
)
from cirecon.memory import MemoryContext


def test_agent_state_initializes():
    state = AgentState()
    assert state.scanned_files == []
    assert state.issues_found == []
    assert state.issues_fixed == []
    assert state.unresolved == []
    assert state.iteration == 0
    assert state.tool_history == []
    assert state.patches == []
    assert state.validation_results == []


def test_agent_state_with_initial_issues():
    issues = [{"id": "RULE_001", "message": "test"}]
    state = AgentState(unresolved=issues, issues_found=list(issues))
    assert len(state.unresolved) == 1
    assert state.unresolved[0]["id"] == "RULE_001"


def test_tool_definitions_has_all_tools():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "read_workflow_file" in names
    assert "validate_yaml_schema" in names
    assert "run_rule_checks" in names
    assert "check_secret_exists" in names
    assert "propose_fix" in names
    assert "apply_fix" in names
    assert "create_pr" in names
    assert len(names) == 7


def test_build_context_includes_unresolved():
    state = AgentState(
        unresolved=[{"id": "RULE_A", "message": "Missing permissions", "auto_fixable": True}]
    )
    memory = MemoryContext(repo="test/repo")
    messages = build_context(state, memory)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "RULE_A" in messages[1]["content"]


def test_build_context_includes_rejected_fixes():
    state = AgentState(
        unresolved=[{"id": "RULE_B", "message": "Bad action", "auto_fixable": True}]
    )
    memory = MemoryContext(repo="test/repo", rejected_fixes=["RULE_B"])
    messages = build_context(state, memory)
    assert "RULE_B" in messages[1]["content"]
    assert "rejected" in messages[1]["content"].lower()


@patch("cirecon.agent_loop.read_workflow_file")
def test_dispatch_read_workflow_file(mock_read):
    mock_read.return_value.success = True
    mock_read.return_value.data = {"path": "test.yml", "content": "name: CI"}

    result = dispatch_tool("read_workflow_file", {"path": "test.yml"}, {})
    assert result["success"] is True


@patch("cirecon.agent_loop.run_rule_checks_tool")
def test_dispatch_run_rule_checks(mock_checks):
    mock_checks.return_value.success = True
    mock_checks.return_value.data = {"issues": [], "count": 0}

    result = dispatch_tool("run_rule_checks", {"path": "f.yml", "content": ""}, {})
    assert result["success"] is True


@patch("cirecon.agent_loop.check_secret_exists")
def test_dispatch_check_secret_exists(mock_secret):
    mock_secret.return_value.success = True
    mock_secret.return_value.data = {"exists": True}

    result = dispatch_tool(
        "check_secret_exists",
        {"secret_name": "MY_KEY"},
        {"github_token": "tok", "repo": "test/repo"},
    )
    assert result["success"] is True
    mock_secret.assert_called_with("MY_KEY", "tok", "test/repo")


@patch("cirecon.agent_loop.propose_fix")
def test_dispatch_propose_fix(mock_propose):
    mock_propose.return_value.success = True
    mock_propose.return_value.data = {"patch": "fixed:", "confidence": 0.85}

    state = AgentState(unresolved=[{"id": "RULE_X", "message": "Fix me"}])
    result = dispatch_tool(
        "propose_fix",
        {"issue_id": "RULE_X", "file_section": "some yaml"},
        {"api_key": "sk-key", "state": state},
    )
    assert result["success"] is True
    mock_propose.assert_called_once()


@patch("cirecon.agent_loop.create_branch_and_pr")
def test_dispatch_create_pr(mock_create_pr):
    mock_create_pr.return_value.success = True
    mock_create_pr.return_value.data = {"pr_url": "https://github.com/test/repo/pull/1"}

    state = AgentState()
    context = {"github_token": "tok", "repo": "test/repo", "state": state}
    result = dispatch_tool("create_pr", {}, context)
    assert result["success"] is True
    mock_create_pr.assert_called_once()


@patch("cirecon.agent_loop._call_claude")
def test_run_agent_loop_no_issues(mock_claude):
    issues = []
    memory = MemoryContext(repo="test/repo")
    state = run_agent_loop(issues, memory, "sk-key", max_iterations=5)
    assert state.iteration == 0
    assert state.unresolved == []
    mock_claude.assert_not_called()


@patch("cirecon.agent_loop._call_claude")
def test_run_agent_loop_stops_at_max_iterations(mock_claude):
    mock_claude.return_value = {
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_workflow_file",
                "input": {"path": "test.yml"},
            }
        ]
    }

    issues = [{"id": "RULE_X", "message": "Fix", "auto_fixable": True}]
    memory = MemoryContext(repo="test/repo")
    state = run_agent_loop(
        issues, memory, "sk-key", max_iterations=3, repo="test/repo", github_token="tok"
    )

    assert state.iteration <= 3
    assert mock_claude.call_count <= 3


@patch("cirecon.agent_loop._call_claude")
def test_run_agent_loop_infinite_loop_guard(mock_claude):
    mock_claude.return_value = {
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_workflow_file",
                "input": {"path": "test.yml"},
            }
        ]
    }

    issues = [{"id": "RULE_X", "message": "Fix", "auto_fixable": True}]
    memory = MemoryContext(repo="test/repo")
    state = run_agent_loop(
        issues, memory, "sk-key", max_iterations=10, repo="test/repo", github_token="tok"
    )

    warnings = [
        t for t in state.tool_history if "warning" in t
    ]
    assert len(warnings) > 0 or state.iteration < 10


def test_dispatch_unknown_tool():
    result = dispatch_tool("nonexistent", {}, {})
    assert result["success"] is False
    assert "Unknown tool" in result["error"]
