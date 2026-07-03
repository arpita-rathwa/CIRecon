from cirecon.input_layer import discover_workflow_files
from cirecon.rule_engine import run_all_checks
def run():
    files = discover_workflow_files(".")
    for path, content in files:
        issues = run_all_checks(path, content)
        for issue in issues:
            print(f"[{issue.severity.value.upper()}] {issue.id}: {issue.message}")
if __name__ == "__main__":
    run()            