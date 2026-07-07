import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cirecon.memory import (
    FixRecord,
    MemoryContext,
    get_recurring_issues,
    load_memory,
    record_detection,
    record_fix,
    record_rejected_fix,
    save_memory,
    was_fix_rejected,
    was_issue_recently_fixed,
)
from cirecon.rule_engine import Issue, Location, Severity


def test_save_and_load_roundtrip():
    ctx = MemoryContext(
        repo="test/repo",
        total_runs=3,
        fixes=[
            FixRecord(
                issue_id="RULE_001",
                file=".github/workflows/ci.yml",
                fix_applied="bump actions/checkout@v2 -> v4",
                detected_at="2026-01-01T00:00:00+00:00",
                run_count=2,
            )
        ],
        rejected_fixes=["RULE_002"],
        known_secrets=["MY_SECRET"],
    )
    with tempfile.TemporaryDirectory() as tmp:
        save_memory(ctx, tmp)
        loaded = load_memory(tmp)

    assert loaded.repo == "test/repo"
    assert loaded.total_runs == 3
    assert len(loaded.fixes) == 1
    assert loaded.fixes[0].issue_id == "RULE_001"
    assert loaded.fixes[0].file == ".github/workflows/ci.yml"
    assert loaded.fixes[0].detected_at == "2026-01-01T00:00:00+00:00"
    assert loaded.fixes[0].run_count == 2
    assert loaded.rejected_fixes == ["RULE_002"]
    assert loaded.known_secrets == ["MY_SECRET"]


def test_load_missing_file_returns_empty():
    mem_file = Path(".cirecon-memory/memory.json")
    if mem_file.exists():
        mem_file.unlink()
    ctx = load_memory("/nonexistent")
    assert ctx.total_runs == 0
    assert ctx.fixes == []
    assert ctx.rejected_fixes == []


def test_save_creates_directory():
    ctx = MemoryContext(repo="test/repo")
    mem_file = Path(".cirecon-memory/memory.json")
    if mem_file.exists():
        mem_file.unlink()
    save_memory(ctx, ".")
    assert mem_file.exists()
    raw = json.loads(mem_file.read_text())
    assert raw["repo"] == "test/repo"
    mem_file.unlink()


def test_record_fix_appends():
    ctx = MemoryContext(repo="test/repo")
    fix = FixRecord(
        issue_id="RULE_001",
        file="f.yml",
        fix_applied="bump v2->v4",
        detected_at="2026-01-01T00:00:00+00:00",
        run_count=1,
    )
    record_fix(ctx, fix)
    assert len(ctx.fixes) == 1
    assert ctx.fixes[0].issue_id == "RULE_001"


def test_record_rejected_fix_deduplicates():
    ctx = MemoryContext(repo="test/repo")
    record_rejected_fix(ctx, "RULE_BAD")
    record_rejected_fix(ctx, "RULE_BAD")
    assert ctx.rejected_fixes == ["RULE_BAD"]


def test_record_detection_new():
    ctx = MemoryContext(repo="test/repo")
    issue = Issue(
        id="RULE_001",
        severity=Severity.MEDIUM,
        message="old action",
        location=Location(file="ci.yml", line=5, column=None),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="actions/checkout@v4",
    )
    ctx = record_detection(ctx, issue)
    assert len(ctx.fixes) == 1
    assert ctx.fixes[0].issue_id == "RULE_001"
    assert ctx.fixes[0].file == "ci.yml"
    assert ctx.fixes[0].run_count == 1


def test_record_detection_existing_appends_again():
    ctx = MemoryContext(repo="test/repo")
    issue = Issue(
        id="RULE_001",
        severity=Severity.MEDIUM,
        message="old action",
        location=Location(file="ci.yml", line=5, column=None),
        auto_fixable=True,
        confidence=1.0,
        suggested_fix="actions/checkout@v4",
    )
    ctx = record_detection(ctx, issue)
    ctx = record_detection(ctx, issue)
    assert len(ctx.fixes) == 2
    assert ctx.fixes[0].run_count == 1
    assert ctx.fixes[1].run_count == 1


def test_get_recurring_issues_returns_above_threshold():
    ctx = MemoryContext(repo="test/repo")
    ctx.fixes = [
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
        FixRecord(issue_id="R2", file="b.yml", fix_applied="",
                  detected_at="", run_count=1),
    ]
    recurring = get_recurring_issues(ctx, threshold=3)
    assert "R1" in recurring
    assert "R2" not in recurring


def test_get_recurring_issues_ignores_below_threshold():
    ctx = MemoryContext(repo="test/repo")
    ctx.fixes = [
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
    ]
    recurring = get_recurring_issues(ctx, threshold=3)
    assert recurring == []


def test_was_issue_recently_fixed_returns_true():
    ctx = MemoryContext(repo="test/repo")
    ctx.fixes = [
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
    ]
    assert was_issue_recently_fixed(ctx, "R1", "a.yml") is True


def test_was_issue_recently_fixed_returns_false_for_old_fix():
    ctx = MemoryContext(repo="test/repo")
    ctx.fixes = [
        FixRecord(issue_id="R1", file="a.yml", fix_applied="",
                  detected_at="", run_count=1),
    ]
    # outside the default window of 5
    assert was_issue_recently_fixed(ctx, "R2", "b.yml") is False


def test_was_fix_rejected():
    ctx = MemoryContext(repo="test/repo")
    record_rejected_fix(ctx, "RULE_BAD")
    assert was_fix_rejected(ctx, "RULE_BAD") is True
    assert was_fix_rejected(ctx, "RULE_GOOD") is False
