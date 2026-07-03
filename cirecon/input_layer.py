from pathlib import Path

def discover_workflow_files(repo_path: str) -> list[tuple[str, str]]:
    p = Path(repo_path)
    yml_files = list(p.glob(".github/workflows/*.yml"))
    yaml_files = list(p.glob(".github/workflows/*.yaml"))
    all_files = yml_files + yaml_files

    results = []
    for file_path in all_files:
        content = file_path.read_text(encoding="utf-8")
        results.append((str(file_path), content))
    return results

