#!/usr/bin/env python3
"""Run the useful, credential-free parts of a repo's CI checks locally.

Different consumer repos run entirely different stacks (allotmint: pytest/npm/CDK;
allotmint-mcp: Maven/Java; future repos: who knows), so there is no one check list
that fits every repo this package is installed into. The check list is read from a
`.cicaid-checks.toml` file in the target repo's root; DEFAULT_CHECKS (allotmint's
own checks) is only a fallback for repos that haven't added one yet.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_root  # noqa: E402

CONFIG_FILENAME = ".cicaid-checks.toml"


@dataclass(frozen=True)
class Check:
    """A local check and the workflow that it mirrors."""

    name: str
    description: str
    workflow: str
    commands: tuple[str, ...]


# Fallback used only when the target repo has no .cicaid-checks.toml of its own.
# This is allotmint's own check list -- not a generic default, just what this
# package happened to ship with first. Every other consumer repo should add its
# own config (see README) rather than rely on this.
DEFAULT_CHECKS = (
    Check(
        "backend",
        "Backend integration tests, coverage, type checks, and contract sync",
        ".github/workflows/backend-integration.yml",
        (
            "python scripts/check_contract_version_sync.py",
            "python -m mypy backend --config-file mypy.ini --show-error-codes --pretty --explicit-package-bases",
            "pytest --no-cov tests/backend/common/test_data_provider_parity.py -q",
            "pytest tests --ignore=tests/live --cov=backend --cov-report=xml --cov-report=term --cov-fail-under=80 -q",
        ),
    ),
    Check(
        "frontend",
        "Frontend lint, type checking, unit tests, and dependency audit",
        ".github/workflows/frontend-tests.yml and .github/workflows/ci.yml",
        (
            "npm --prefix frontend run lint",
            "npm --prefix frontend run type-check",
            "npm --prefix frontend test -- --run --coverage",
            "npm --prefix frontend audit --audit-level=high",
        ),
    ),
    Check(
        "infrastructure",
        "CDK tests and GitHub Actions workflow lint",
        ".github/workflows/ci.yml and .github/workflows/cdk-dry-run.yml",
        (
            "pytest cdk/tests/ --no-cov",
            "actionlint",
        ),
    ),
    Check(
        "scripts",
        "Bash developer script tests, plus shellcheck",
        ".github/workflows/ci.yml",
        (
            "npx --yes bats@1.13.0 tests/bash/*.bats",
            "shellcheck .github/scripts/*.sh",
        ),
    ),
    Check(
        "backend-deps",
        "Backend requirements.txt dependency-conflict dry-run",
        ".github/workflows/ci.yml (validate-backend-deps)",
        ("pip install --dry-run -r backend/requirements.txt",),
    ),
)


def _parse_config(text: str, source: str) -> tuple[Check, ...]:
    """Parse a .cicaid-checks.toml document into Check objects.

    Expected shape:
        [[checks]]
        name = "backend"
        description = "..."
        workflow = ".github/workflows/ci.yml"
        commands = ["mvn -B verify"]
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"Failed to parse {source}: {exc}") from exc

    entries = data.get("checks")
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"{source} has no [[checks]] entries.")

    checks = []
    for index, entry in enumerate(entries):
        try:
            checks.append(
                Check(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    workflow=entry.get("workflow", ""),
                    commands=tuple(entry["commands"]),
                )
            )
        except KeyError as exc:
            raise SystemExit(f"{source}: checks[{index}] is missing required key {exc}") from exc
    return tuple(checks)


def load_checks(root: Path, config_path: Path | None = None) -> tuple[Check, ...]:
    """Load this repo's check list from .cicaid-checks.toml, or fall back to DEFAULT_CHECKS.

    An explicit --config path that doesn't exist is an error (the user asked for a
    specific file); the default CONFIG_FILENAME lookup in the repo root is optional
    and silently falls back so repos that haven't added a config yet still work.
    """
    path = config_path or (root / CONFIG_FILENAME)
    if not path.exists():
        if config_path is not None:
            raise SystemExit(f"--config {path} does not exist.")
        return DEFAULT_CHECKS
    return _parse_config(path.read_text(encoding="utf-8"), str(path))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--check", action="append", help="check to run (by name); repeatable")
    selection.add_argument("--all", action="store_true", help="run every check")
    selection.add_argument("--list", action="store_true", help="list checks and commands")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"path to a checks config (default: <repo root>/{CONFIG_FILENAME})",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed command")
    return parser.parse_args(argv)


def print_checks(checks: tuple[Check, ...]) -> None:
    """Print the available checks and their exact commands."""
    for index, check in enumerate(checks, start=1):
        print(f"{index}. {check.name}: {check.description}")
        print(f"   Mirrors: {check.workflow}")
        for command in check.commands:
            print(f"   $ {command}")


def prompt_for_checks(checks: tuple[Check, ...]) -> list[Check]:
    """Ask an interactive user which checks to run."""
    print_checks(checks)
    answer = input("Select checks by number (comma-separated), or 'all': ").strip().lower()
    if answer == "all":
        return list(checks)
    try:
        indexes = [int(value.strip()) for value in answer.split(",")]
        if not indexes or any(index < 1 or index > len(checks) for index in indexes):
            raise ValueError
    except ValueError as exc:
        raise SystemExit("Invalid selection; use listed numbers or 'all'.") from exc
    return [checks[index - 1] for index in dict.fromkeys(indexes)]


def select_checks(args: argparse.Namespace, checks: tuple[Check, ...]) -> list[Check]:
    """Resolve flags or the interactive menu to checks."""
    if args.all:
        return list(checks)
    if args.check:
        valid_names = {check.name for check in checks}
        unknown = [name for name in args.check if name not in valid_names]
        if unknown:
            raise SystemExit(
                f"Unknown check(s): {', '.join(unknown)}. Available: {', '.join(sorted(valid_names))}"
            )
        selected = set(args.check)
        return [check for check in checks if check.name in selected]
    if not sys.stdin.isatty():
        raise SystemExit("No check selected. Use --check NAME, --all, or --list.")
    return prompt_for_checks(checks)


def run_checks(checks: list[Check], root: Path, dry_run: bool, keep_going: bool) -> int:
    """Run selected commands, returning a process-style status code."""
    failures = 0
    for check in checks:
        print(f"\n== {check.name}: {check.description} ==", flush=True)
        for command in check.commands:
            print(f"$ {command}", flush=True)
            if dry_run:
                continue
            result = subprocess.run(command, cwd=root, shell=True, check=False)
            if result.returncode:
                failures += 1
                print(f"FAILED ({result.returncode}): {command}", file=sys.stderr)
                if not keep_going:
                    return result.returncode
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    root = Path(get_repo_root())
    checks = load_checks(root, args.config)
    if args.list:
        print_checks(checks)
        return 0
    return run_checks(select_checks(args, checks), root, args.dry_run, args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main())
