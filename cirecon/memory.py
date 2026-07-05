import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FixRecord:
    issue_id: str
    file: str
    fix_applied: str
    pr_url: str
    pr_status: str  # "open", "merged", "closed"


@dataclass
class MemoryContext:
    repo: str
    total_runs: int = 0
    fixes: list[FixRecord] = field(default_factory=list)
    rejected_fixes: list[str] = field(default_factory=list)
    known_secrets: list[str] = field(default_factory=list)


def _memory_file_path(path: str) -> Path:
    return Path(path) / ".github" / "cirecon" / "memory.json"


def _fix_record_to_dict(r: FixRecord) -> dict:
    return asdict(r)


def _fix_record_from_dict(d: dict) -> FixRecord:
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


def update_pr_status(memory: MemoryContext, pr_url: str, status: str) -> MemoryContext:
    for fix in memory.fixes:
        if fix.pr_url == pr_url:
            fix.pr_status = status
            if status == "closed":
                record_rejected_fix(memory, fix.issue_id)
            break
    return memory


def was_fix_rejected(memory: MemoryContext, issue_id: str) -> bool:
    return issue_id in memory.rejected_fixes
