"""Onboard the current repo to leonarduk/issue-worm.

Automates the manual recipe this project's own operator used to repeat by
hand for every consumer repo (see leonarduk/sing-attune#941): write the
label-gated `.github/workflows/issue-worm.yml`, create the `issue-worm` +
scheduler labels (`in-progress` / `pr-opened` / `needs-help`), gitignore
`.issue-worm/` and `.issue-worm-workspace/`, and scaffold a starter
`.cicaid-checks.toml` (see run_ci_checks.py -- a repo with none of those
made every `cicaid run-ci-checks` run fail on someone else's unrelated
commands, see leonarduk/cicaid#43).

Deliberately never touches the `WORM_PAT` secret: that's a credential, and
creating or rotating secrets on the user's behalf is out of scope for this
tool. The command prints a reminder instead.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info, get_repo_root  # noqa: E402

WORKFLOW_PATH = ".github/workflows/issue-worm.yml"
CHECKS_CONFIG_PATH = ".cicaid-checks.toml"
GITIGNORE_ENTRIES = (".issue-worm/", ".issue-worm-workspace/")

GH_TIMEOUT_SECONDS = 30

# name -> (color, description). Matches the labels already created by hand
# on leonarduk/sing-attune (issue-worm#941) so newly onboarded repos look
# the same as the first one.
LABELS: dict[str, tuple[str, str]] = {
    "issue-worm": ("5319E7", "Apply to dispatch issue-worm (free engine) against this issue"),
    "in-progress": ("FBCA04", "issue-worm scheduler: claimed, build in progress"),
    "pr-opened": ("0E8A16", "issue-worm scheduler: PR opened"),
    "needs-help": ("B60205", "issue-worm scheduler: gave up, needs a human"),
}

WORKFLOW_TEMPLATE = """\
name: issue-worm

# Label-gated dispatch of leonarduk/issue-worm's free engine: applying the
# `issue-worm` label to an issue runs a single-pass coder against it and
# opens a PR. Scaffolded by `cicaid onboard-issue-worm`.
#
# The `if:` guard below is LOAD-BEARING, not cosmetic. The action pushes and
# opens the PR with WORM_PAT (so the PR triggers this repo's own CI and
# review workflows), and a PAT-driven label write would also re-trigger this
# `labeled` workflow. Without the guard, issue-worm-pro's scheduler labels
# (in-progress / pr-opened / needs-help) would loop. Do not remove it.
on:
  issues:
    types: [labeled]

concurrency:
  group: issue-worm-${{{{ github.event.issue.number }}}}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  build:
    if: github.event.label.name == 'issue-worm'
    runs-on: {runs_on}
    timeout-minutes: 30
    steps:
      # {pin}: the floating action tag that leonarduk/issue-worm's release
      # workflow moves to each newest vX.Y.Z release, so fixes arrive
      # without editing this file. Repin only for a breaking action.yml
      # input change.
      - uses: leonarduk/issue-worm@{pin}
        with:
          issue: ${{{{ github.event.issue.number }}}}
          # A fine-grained PAT (or GitHub App token) with `contents: write`,
          # `pull-requests: write`, and `issues: read` on this repo -- see
          # action.yml's github-token input. The default GITHUB_TOKEN can't
          # be used: a PR pushed with it wouldn't trigger this repo's own
          # CI. You must create this secret yourself -- see the printed
          # reminder after this command finishes.
          github-token: ${{{{ secrets.WORM_PAT }}}}
{env_block}
"""

CLOUD_ENV_BLOCK = """\
        env:
          # cloud -> DeepSeek, via the OpenAI-compatible coder. __RUNS_ON_NOTE__
          CODER_MODEL_SOURCE: cloud
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
"""

CHECKS_TOML_STUB = """\
# Local check list for `cicaid run-ci-checks` (used by issue-worm's verifier
# stage). There is no generic default -- see run_ci_checks.py -- so this
# file is required. `cicaid onboard-issue-worm` could not confidently detect
# this repo's real checks; fill in the TODO below with the actual test/lint
# commands this repo's own CI runs (see .github/workflows/*.yml), or delete
# whichever example checks below don't apply.

[[checks]]
name = "tests"
description = "TODO: describe what this runs"
workflow = "TODO: path to the GitHub Actions workflow this mirrors"
commands = [
    "TODO: e.g. pytest, npm test, mvn -B verify, ...",
]
"""


def render_workflow(runs_on: str, pin: str, model_source: str) -> str:
    """Build the issue-worm.yml content for the given runner/pin/model source."""
    if model_source == "cloud":
        runs_on_note = (
            "hosted runners have no route to a local Ollama host, so `local` "
            "(the engine's default) isn't usable here."
            if runs_on == "ubuntu-latest"
            else "DEEPSEEK_API_KEY must already be a repo secret."
        )
        # A plain replace, not .format(): the block's ${{ ... }} GitHub Actions
        # expression syntax must survive untouched, and .format() collapses
        # doubled braces (its own escaping rule) whether or not a field with
        # that name is being substituted.
        env_block = "\n" + CLOUD_ENV_BLOCK.replace("__RUNS_ON_NOTE__", runs_on_note)
    else:
        env_block = ""
    return WORKFLOW_TEMPLATE.format(runs_on=runs_on, pin=pin, env_block=env_block)


def ensure_gitignore_entries(root: Path, *, dry_run: bool = False) -> list[str]:
    """Append any missing GITIGNORE_ENTRIES to root/.gitignore. Returns what was added."""
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in existing_lines]
    if not missing or dry_run:
        return missing
    separator = "" if not existing or existing.endswith("\n") else "\n"
    addition = "\n".join(missing) + "\n"
    gitignore.write_text(existing + separator + addition, encoding="utf-8")
    return missing


def detect_checks_config(root: Path) -> str | None:
    """Best-effort guess at a real .cicaid-checks.toml, or None if unsure.

    Deliberately conservative: a wrong guess here just reproduces the exact
    bug this tool exists to prevent (silently running the wrong commands).
    Only returns something when a single, unambiguous, well-known test
    command is detected; otherwise the caller should fall back to
    CHECKS_TOML_STUB and let a human fill it in.
    """
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
        pytest_cfg = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        testpaths = pytest_cfg.get("testpaths")
        if testpaths:
            path = " ".join(testpaths) if isinstance(testpaths, list) else str(testpaths)
            uses_uv = (root / "uv.lock").exists()
            command = f"uv run pytest {path} -q" if uses_uv else f"pytest {path} -q"
            return _render_single_check(
                name="tests",
                description="Unit test suite",
                workflow="(detected from pyproject.toml's [tool.pytest.ini_options])",
                command=command,
            )

    package_json = root / "package.json"
    if package_json.exists():
        import json

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if "test" in data.get("scripts", {}):
            return _render_single_check(
                name="tests",
                description="npm test suite",
                workflow="(detected from package.json's scripts.test)",
                command="npm test",
            )

    return None


def _render_single_check(*, name: str, description: str, workflow: str, command: str) -> str:
    return (
        "# Local check list for `cicaid run-ci-checks` (used by issue-worm's verifier\n"
        "# stage). Auto-detected by `cicaid onboard-issue-worm` -- double-check this\n"
        "# actually matches what this repo's real CI runs before relying on it.\n\n"
        "[[checks]]\n"
        f'name = "{name}"\n'
        f'description = "{description}"\n'
        f'workflow = "{workflow}"\n'
        f'commands = [\n    "{command}",\n]\n'
    )


def ensure_checks_config(root: Path, *, dry_run: bool = False) -> str | None:
    """Write CHECKS_CONFIG_PATH if it doesn't exist yet. Returns what was written, if any."""
    path = root / CHECKS_CONFIG_PATH
    if path.exists():
        return None
    content = detect_checks_config(root) or CHECKS_TOML_STUB
    if not dry_run:
        path.write_text(content, encoding="utf-8")
    return content


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a single `gh` CLI command. Never raises."""
    cmd = ["gh", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="", stderr=f"gh {' '.join(args)} timed out"
        )


def ensure_labels(owner: str, repo: str, *, dry_run: bool = False) -> list[str]:
    """Create (or update) each of LABELS on owner/repo. Returns the names touched."""
    touched = []
    for name, (color, description) in LABELS.items():
        touched.append(name)
        if dry_run:
            continue
        # --force both creates the label if missing and updates color/description
        # if it already exists, so this is safe to re-run.
        run_gh(
            [
                "label",
                "create",
                name,
                "--repo",
                f"{owner}/{repo}",
                "--color",
                color,
                "--description",
                description,
                "--force",
            ]
        )
    return touched


def worm_pat_instructions(owner: str, repo: str) -> str:
    """Render the step-by-step WORM_PAT recipe for ``owner/repo``.

    This command never creates the secret itself (see the module docstring),
    so what it prints *is* the whole handover -- it has to be followable by
    someone who has never made a fine-grained PAT. Says the same things as
    the recipe issue-worm-pro's dashboard puts in its setup PR
    (leonarduk/issue-worm-pro#1813), but as plain text: this is terminal
    output, not a PR body, so no markdown tables and short enough to read
    in a shell. Permissions are issue-worm's README "Inputs" table,
    `github-token` row -- the authoritative list.
    """
    return f"""Creating the WORM_PAT secret
  `secrets.GITHUB_TOKEN` cannot stand in for it: a push made with the built-in
  token deliberately does not trigger other workflows, so the PR issue-worm
  opens would never get a CI run, a review, or a required check.

  1. Open https://github.com/settings/personal-access-tokens/new
  2. Token name: anything you'll recognise later. Expiration: your call --
     issue-worm starts failing with a 401 the day it expires, so calendar
     the rotation.
  3. Resource owner:
       {owner}
     If that is an organisation rather than your own account, an org owner
     has to approve the token before it works.
  4. Repository access: "Only select repositories", then:
       {owner}/{repo}
  5. Repository permissions -- these three, and nothing else is needed
     (read-only Metadata is added for you):
       Contents        Read and write   push issue-worm's branch
       Pull requests   Read and write   open the pull request
       Issues          Read and write   read: the issue body; write: the live
                                        progress comment and self-heal saving
                                        its drafted section back onto the issue
     `issues: read` is the one people miss -- only the issue-body fetch needs
     it, and that runs, and fails, before the push and PR steps ever do.
     `issues: write` is optional: without it those two features silently
     no-op rather than failing the build. Add Workflows: read and write only
     if issue-worm should be allowed to edit files under .github/workflows/.
  6. Generate token, then copy it -- GitHub shows it exactly once.
  7. Paste it in at
     https://github.com/{owner}/{repo}/settings/secrets/actions/new
     -- that is Settings -> Secrets and variables -> Actions, then New
     repository secret. Name it WORM_PAT, paste the token in, Add secret.

  Or a classic token: https://github.com/settings/tokens/new with the single
  `repo` scope covers all three permissions above (tick `workflow` too for the
  same caveat). It is much coarser -- a classic token reaches every repo its
  owner can -- so prefer the fine-grained one where you have the choice.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        choices=("hosted", "self-hosted"),
        default="hosted",
        help="GitHub-hosted (ubuntu-latest) or this org's self-hosted runner pool (default: hosted)",
    )
    parser.add_argument(
        "--model-source",
        choices=("local", "cloud"),
        default="local",
        help="issue-worm's coder backend: local Ollama (self-hosted runners only) or "
        "cloud DeepSeek, which needs a DEEPSEEK_API_KEY secret (default: local)",
    )
    parser.add_argument("--pin", default="v1", help="leonarduk/issue-worm action ref to pin (default: v1)")
    parser.add_argument("--skip-labels", action="store_true", help="don't create/update GitHub labels")
    parser.add_argument("--dry-run", action="store_true", help="print what would change without writing anything")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    root = Path(get_repo_root())
    runs_on = "ubuntu-latest" if args.runner == "hosted" else "[self-hosted, linux, x64]"

    if args.model_source == "local" and args.runner == "hosted":
        print(
            "warning: --model-source local has no route to a local Ollama host on "
            "GitHub-hosted runners; pass --model-source cloud, or --runner self-hosted.",
            file=sys.stderr,
        )

    # Needed both for the labels below and for the two repo-specific URLs in
    # the WORM_PAT recipe. A remote we can't read is only fatal for the
    # labels, which actually have to talk to that repo; the recipe falls back
    # to placeholders the reader can substitute themselves.
    try:
        owner, repo = get_repo_info()
    except ValueError:
        if not args.skip_labels:
            raise
        owner, repo = "<owner>", "<name>"

    workflow_path = root / WORKFLOW_PATH
    workflow_content = render_workflow(runs_on, args.pin, args.model_source)
    if not args.dry_run:
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(workflow_content, encoding="utf-8")
    print(f"{'would write' if args.dry_run else 'wrote'} {WORKFLOW_PATH}")

    added_gitignore = ensure_gitignore_entries(root, dry_run=args.dry_run)
    if added_gitignore:
        verb = "would add" if args.dry_run else "added"
        print(f"{verb} to .gitignore: {', '.join(added_gitignore)}")

    checks_written = ensure_checks_config(root, dry_run=args.dry_run)
    if checks_written is None:
        print(f"{CHECKS_CONFIG_PATH} already exists, left unchanged")
    else:
        verb = "would write" if args.dry_run else "wrote"
        stub = checks_written is CHECKS_TOML_STUB or checks_written == CHECKS_TOML_STUB
        note = " (a TODO stub -- fill in this repo's real checks)" if stub else " (auto-detected -- please verify)"
        print(f"{verb} {CHECKS_CONFIG_PATH}{note}")

    if not args.skip_labels:
        touched = ensure_labels(owner, repo, dry_run=args.dry_run)
        verb = "would create/update" if args.dry_run else "created/updated"
        print(f"{verb} labels: {', '.join(touched)}")

    print(
        "\nNext steps (not automated -- these are credentials/require a human):\n"
        "  1. Create the WORM_PAT repo secret -- step-by-step recipe below.\n"
        + (
            "  2. Add a DEEPSEEK_API_KEY repo secret (--model-source cloud was selected).\n"
            if args.model_source == "cloud"
            else ""
        )
        + f"  {'3' if args.model_source == 'cloud' else '2'}. Review and commit {WORKFLOW_PATH}"
        + (f" and {CHECKS_CONFIG_PATH}" if checks_written is not None else "")
        + ".\n"
        "  Apply the `issue-worm` label to an issue to try it.\n"
    )
    print(worm_pat_instructions(owner, repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
