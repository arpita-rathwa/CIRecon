import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cirecon.rule_engine import Issue


@dataclass
class FixRecord:
    issue_id: str
    file: str
    detection_note: str
    detected_at: str  # ISO timestamp
    run_count: int    # how many times this issue has been seen


@dataclass
class MemoryContext:
    repo: str
    total_runs: int = 0
    fixes: list[FixRecord] = field(default_factory=list)
    rejected_fixes: list[str] = field(default_factory=list)
    known_secrets: list[str] = field(default_factory=list)


def _memory_file_path(path: str) -> Path:
    return Path(path) / ".cirecon-memory" / "memory.json"


def _fix_record_to_dict(r: FixRecord) -> dict:
    return asdict(r)


def _fix_record_from_dict(d: dict) -> FixRecord:
    if "fix_applied" in d and "detection_note" not in d:
        d["detection_note"] = d.pop("fix_applied")
    return FixRecord(**d)


def load_memory(path: str) -> MemoryContext:
    mem_file = _memory_file_path(path)
    if not mem_file.exists():
        return MemoryContext(repo=path)
    raw = mem_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    data["fixes"] = [_fix_record_from_dict(f) for f in data.get("fixes", [])]
    return MemoryContext(**data)


def save_memory(memory: MemoryContext, path: str) -> None:
    mem_file = _memory_file_path(path)
    mem_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "repo": memory.repo,
        "total_runs": memory.total_runs,
        "fixes": [_fix_record_to_dict(f) for f in memory.fixes],
        "rejected_fixes": memory.rejected_fixes,
        "known_secrets": memory.known_secrets,
    }
    mem_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_fix(memory: MemoryContext, fix: FixRecord) -> MemoryContext:
    memory.fixes.append(fix)
    return memory


def record_rejected_fix(memory: MemoryContext, issue_id: str) -> MemoryContext:
    if issue_id not in memory.rejected_fixes:
        memory.rejected_fixes.append(issue_id)
    return memory


def record_detection(memory: MemoryContext, issue: Issue) -> MemoryContext:
    memory.fixes.append(FixRecord(
        issue_id=issue.id,
        file=issue.location.file,
        detection_note=issue.suggested_fix or "detected",
        detected_at=datetime.now(timezone.utc).isoformat(),
        run_count=1,
    ))
    return memory


def get_recurring_issues(memory: MemoryContext, threshold: int = 3) -> list[str]:
    from collections import Counter
    counts = Counter(f.issue_id for f in memory.fixes)
    return [issue_id for issue_id, count in counts.items() if count >= threshold]


def was_issue_recently_fixed(
    memory: MemoryContext, issue_id: str, file: str, within_runs: int = 5
) -> bool:
    recent = memory.fixes[-(within_runs):]
    return any(f.issue_id == issue_id and f.file == file for f in recent)


def was_fix_rejected(memory: MemoryContext, issue_id: str) -> bool:
    return issue_id in memory.rejected_fixes
