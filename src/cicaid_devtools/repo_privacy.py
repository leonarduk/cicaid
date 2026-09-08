"""Prepare a repo for going private (self-hosted runners) or reverse it back to public

Automates the manual steps used in leonarduk/sing-attune#904: rewrite
``.github/workflows/*.yml`` ``runs-on: ubuntu-latest`` / ``runs-on: windows-latest``
lines to self-hosted equivalents (keeping the original commented out above so the
change is reversible), remove GitHub-hosted-only workflows (CodeQL, dependency
review) that don't work without GitHub Advanced Security / hosted runners, and drop
an opt-in ``.local_runner`` marker file. ``--to public`` reverses all of that.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info, get_repo_root  # noqa: E402

MARKER_FILE = ".local_runner"

REMOVABLE_WORKFLOWS = ("codeql.yml", "dependency-review.yml")

SELF_HOSTED_MAP = {
    "ubuntu-latest": "[self-hosted, linux, x64]",
    "windows-latest": "[self-hosted, windows, x64]",
}

# Matches a top-level (or job-indented) scalar `runs-on: ubuntu-latest` /
# `runs-on: windows-latest` line -- not a list, and not already self-hosted.
_FORWARD_RE = re.compile(r"^(?P<indent>\s*)runs-on:\s*(?P<value>ubuntu-latest|windows-latest)\s*$")

# Matches a previously-commented original line immediately followed (next
# line, checked separately) by the self-hosted replacement.
_COMMENTED_RE = re.compile(
    r"^(?P<indent>\s*)#\s*runs-on:\s*(?P<value>ubuntu-latest|windows-latest)\s*$"
)
_SELF_HOSTED_RE = re.compile(r"^(?P<indent>\s*)runs-on:\s*\[self-hosted.*\]\s*$")

CODEQL_WORKFLOW = """\
name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "30 4 * * 1"

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      fail-fast: false
      matrix:
        language: ['python']
    steps:
      - uses: actions/checkout@v7
      - uses: github/codeql-action/init@v4
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/analyze@v4
        with:
          category: "/language:${{ matrix.language }}"
"""

DEPENDENCY_REVIEW_WORKFLOW = """\
name: Dependency Review

on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/dependency-review-action@v5.0.0
        with:
          fail-on-severity: high
"""

TEMPLATES = {
    "codeql.yml": CODEQL_WORKFLOW,
    "dependency-review.yml": DEPENDENCY_REVIEW_WORKFLOW,
}


@dataclass
class Report:
    """Collects what changed (or would change) for the final printout."""

    workflows_converted: list[str] = field(default_factory=list)
    workflows_reverted: list[str] = field(default_factory=list)
    workflows_flagged: list[str] = field(default_factory=list)
    workflows_removed: list[str] = field(default_factory=list)
    workflows_restored: list[str] = field(default_factory=list)
    marker_added: bool = False
    marker_removed: bool = False


def _convert_to_private(text: str) -> tuple[str, bool]:
    """Rewrite scalar hosted `runs-on:` lines to commented + self-hosted.

    Idempotent: a line already commented out (or already self-hosted) is left
    alone.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").rstrip("\r")
        match = _FORWARD_RE.match(stripped)
        if match:
            # Skip if the previous emitted line is already the commented
            # original (defensive; shouldn't normally happen since the
            # original scalar line itself would have been rewritten already).
            indent = match.group("indent")
            value = match.group("value")
            newline = "\n" if line.endswith("\n") else ""
            out.append(f"{indent}# runs-on: {value}{newline}")
            out.append(f"{indent}runs-on: {SELF_HOSTED_MAP[value]}{newline}")
            changed = True
        else:
            out.append(line)
        i += 1
    return "".join(out), changed


def _convert_to_public(text: str) -> tuple[str, bool, bool]:
    """Reverse `_convert_to_private`.

    Returns (new_text, changed, has_unrevertable_self_hosted).
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    flagged = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").rstrip("\r")
        comment_match = _COMMENTED_RE.match(stripped)
        if comment_match and i + 1 < len(lines):
            next_stripped = lines[i + 1].rstrip("\n").rstrip("\r")
            self_hosted_match = _SELF_HOSTED_RE.match(next_stripped)
            if self_hosted_match and self_hosted_match.group("indent") == comment_match.group(
                "indent"
            ):
                indent = comment_match.group("indent")
                value = comment_match.group("value")
                newline = "\n" if line.endswith("\n") else ""
                out.append(f"{indent}runs-on: {value}{newline}")
                changed = True
                i += 2
                continue
        self_hosted_match = _SELF_HOSTED_RE.match(stripped)
        if self_hosted_match:
            # A self-hosted line with no commented original above it -- can't
            # auto-revert, leave alone and flag.
            flagged = True
        out.append(line)
        i += 1
    return "".join(out), changed, flagged


def _iter_workflow_files(root: Path) -> list[Path]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    return sorted(p for p in workflows_dir.glob("*.yml") if p.is_file()) + sorted(
        p for p in workflows_dir.glob("*.yaml") if p.is_file()
    )


def to_private(root: Path, dry_run: bool) -> Report:
    """Convert workflows to self-hosted runners and drop hosted-only workflows."""
    report = Report()

    for path in _iter_workflow_files(root):
        text = path.read_text(encoding="utf-8")
        new_text, changed = _convert_to_private(text)
        if changed:
            report.workflows_converted.append(path.relative_to(root).as_posix())
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")

    for name in REMOVABLE_WORKFLOWS:
        path = root / ".github" / "workflows" / name
        if path.exists():
            report.workflows_removed.append(path.relative_to(root).as_posix())
            if not dry_run:
                path.unlink()

    marker = root / MARKER_FILE
    if not marker.exists():
        report.marker_added = True
        if not dry_run:
            marker.write_text("", encoding="utf-8")

    return report


def to_public(root: Path, dry_run: bool) -> Report:
    """Reverse `to_private`: restore hosted runs-on and hosted-only workflows."""
    report = Report()

    for path in _iter_workflow_files(root):
        text = path.read_text(encoding="utf-8")
        new_text, changed, flagged = _convert_to_public(text)
        rel = path.relative_to(root).as_posix()
        if changed:
            report.workflows_reverted.append(rel)
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")
        if flagged:
            report.workflows_flagged.append(rel)

    for name, content in TEMPLATES.items():
        path = root / ".github" / "workflows" / name
        if not path.exists():
            report.workflows_restored.append(path.relative_to(root).as_posix())
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

    marker = root / MARKER_FILE
    if marker.exists():
        report.marker_removed = True
        if not dry_run:
            marker.unlink()

    return report


def _print_private_report(
    report: Report, dry_run: bool, owner: str | None, repo: str | None
) -> None:
    verb = "Would convert" if dry_run else "Converted"
    if report.workflows_converted:
        print(f"{verb} runs-on to self-hosted in:")
        for name in report.workflows_converted:
            print(f"  - {name}")
    else:
        print("No workflows needed a runs-on conversion.")

    verb = "Would remove" if dry_run else "Removed"
    if report.workflows_removed:
        print(f"{verb} GitHub-hosted-only workflow(s):")
        for name in report.workflows_removed:
            print(f"  - {name}")
    else:
        print("No GitHub-hosted-only workflows present to remove.")

    if report.marker_added:
        verb = "Would add" if dry_run else "Added"
        print(f"{verb} marker file: {MARKER_FILE}")
    else:
        print(f"Marker file {MARKER_FILE} already present.")

    print("\nManual follow-up checklist:")
    print("  [ ] Bring up a self-hosted Linux runner pool for the repo and confirm")
    if owner and repo:
        print(f"      runners show 'online' via: gh api repos/{owner}/{repo}/actions/runners")
    else:
        print("      runners show 'online' via: gh api repos/<owner>/<repo>/actions/runners")
    if any("windows-latest" in name or True for name in report.workflows_converted):
        print("  [ ] If any workflow runs Windows jobs, add this repo to the host's")
        print("      windows-pools.conf and start that runner fleet.")
    print("  [ ] Update branch protection required status checks to drop checks")
    print("      that no longer report, e.g. 'Analyze (python)' and 'dependency-review'.")
    print("  [ ] Confirm the next PR's workflows actually pick up a self-hosted runner.")


def _print_public_report(report: Report, dry_run: bool) -> None:
    verb = "Would restore" if dry_run else "Restored"
    if report.workflows_reverted:
        print(f"{verb} original runs-on in:")
        for name in report.workflows_reverted:
            print(f"  - {name}")
    else:
        print("No workflows had a commented original runs-on to restore.")

    if report.workflows_flagged:
        print("Could not auto-revert (no commented original found), left as-is:")
        for name in report.workflows_flagged:
            print(f"  - {name}")

    verb = "Would restore" if dry_run else "Restored"
    if report.workflows_restored:
        print(f"{verb} GitHub-hosted-only workflow(s) from template:")
        for name in report.workflows_restored:
            print(f"  - {name}")
    else:
        print("GitHub-hosted-only workflows already present (or none restored).")

    if report.marker_removed:
        verb = "Would remove" if dry_run else "Removed"
        print(f"{verb} marker file: {MARKER_FILE}")
    else:
        print(f"Marker file {MARKER_FILE} was not present.")

    print("\nManual follow-up checklist:")
    print("  [ ] Confirm GitHub Advanced Security / CodeQL is enabled for the now-public repo.")
    print("  [ ] Re-add 'Analyze (python)' and 'dependency-review' to branch protection")
    print("      required status checks.")
    print("  [ ] Consider tearing down dedicated self-hosted runner pools if no longer needed.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        choices=("private", "public"),
        required=True,
        help="direction to convert the repo's workflows",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change without writing"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    root = Path(get_repo_root())

    try:
        owner, repo = get_repo_info()
    except ValueError:
        owner = repo = None

    if args.to == "private":
        report = to_private(root, args.dry_run)
        _print_private_report(report, args.dry_run, owner, repo)
    else:
        report = to_public(root, args.dry_run)
        _print_public_report(report, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
