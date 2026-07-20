import subprocess
import sys


def _run(cmd: list[str]) -> int:
    result = subprocess.run(cmd)
    return result.returncode


def lint() -> None:
    sys.exit(_run(["ruff", "check", "cirecon/", "tests/"]))


def typecheck() -> None:
    sys.exit(_run(["mypy", "cirecon/", "--ignore-missing-imports"]))


def check() -> None:
    lint_code = _run(["ruff", "check", "cirecon/", "tests/"])
    type_code = _run(["mypy", "cirecon/", "--ignore-missing-imports"])
    if lint_code != 0 or type_code != 0:
        sys.exit(1)
    sys.exit(0)
