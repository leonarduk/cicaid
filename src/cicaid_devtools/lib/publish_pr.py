"""CLI tool to publish a PR from the current branch with optional LLM assistance
(Ollama or LM Studio)."""

from __future__ import annotations
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import requests


from cicaid_devtools.lib.github_repo import get_repo_info, get_actual_repo_name, is_wiki_repo  # shared implementation


def get_current_branch() -> str:
    """Get the current branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        logger.error(f"Failed to get current branch: {exc}")
        sys.exit(1)

def extract_issue_id(branch_name: str) -> Optional[int]:
    """Extract issue ID from branch name (e.g., 'fix/issue-4445-slug' -> 4445)."""
    match = re.search(r"issue-(\d+)", branch_name)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", branch_name)
    if match:
        return int(match.group(1))
    return None


def get_default_branch(owner: str, repo: str) -> str:
    """Get the default branch name."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "main"
    except subprocess.CalledProcessError:
        pass
    return "main"


def check_working_tree_clean() -> bool:
    """Check if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return not result.stdout.strip()
    except subprocess.CalledProcessError:
        return False


def get_changed_files(branch: str, default_branch: str = "main") -> list[str]:
    """Get list of changed files: either uncommitted changes or commits on the branch."""
    changed_files = []
    remote_default_branch = f"origin/{default_branch or 'main'}"
    try:
        # Check for both staged and unstaged changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            uncommitted_changes = result.stdout.strip().split("\n")
            changed_files.extend(uncommitted_changes)

        # Check for commits on the branch only if we have a merge base
        result = subprocess.run(
            ["git", "merge-base", branch, remote_default_branch],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            merge_base = result.stdout.strip()
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{merge_base}...HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                committed_changes = result.stdout.strip().split("\n")
                changed_files.extend(committed_changes)

    except subprocess.CalledProcessError:
        pass

    # remove duplicates
    return list(set(changed_files))


def stage_and_commit(files: Optional[list[str]], message: str, branch: str, default_branch: str = "main") -> bool:
    """Stage and commit the specified files (or changed files in branch if none specified)."""
    try:
        if not files:
            # Auto-detect changed files in the branch
            files = get_changed_files(branch, default_branch)
            if not files:
                logger.error("No changed files found in branch. Nothing to commit.")
                return False

        # Stage specified files
        for f in files:
            subprocess.run(["git", "add", f], check=True)

        subprocess.run(["git", "commit", "-m", message], check=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error(f"Failed to commit: {exc}")
        return False


def branch_is_ahead_of_main(branch: str, default_branch: str) -> bool:
    """Check if branch has commits ahead of the default branch.

    Compares against the remote tracking ref so the check works even when
    the local default branch is stale.  Tries ``origin/{default_branch}``,
    ``origin/main``, and ``origin/master`` in order.

    This only checks that the branch has commits the remote base lacks --
    it does not require the branch to also be fully caught up with the
    remote base (i.e. it does not require fast-forward ancestry). A
    long-lived feature branch routinely diverges from a moving default
    branch, and that divergence is not itself a reason to block a PR.
    """
    candidates = [f"origin/{default_branch}", "origin/main", "origin/master"]
    for remote_base in candidates:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", remote_base],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                continue

            result = subprocess.run(
                ["git", "rev-list", "--count", f"{remote_base}..{branch}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) > 0
        except (subprocess.CalledProcessError, ValueError):
            continue
    return False


def push_to_remote(branch: str) -> bool:
    """Push the branch to remote.

    Always passes `-u` so the branch's upstream is set on the first push,
    not just on subsequent ones -- callers don't need the branch to already
    be tracking upstream before calling this.
    """
    try:
        subprocess.run(["git", "push", "-u", "origin", branch], check=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error(f"Failed to push: {exc}")
        return False


def fetch_issue(owner: str, repo: str, issue_id: int) -> Optional[dict]:
    """Fetch issue details via the authenticated `gh` CLI.

    Uses `gh api` (which reuses `gh`'s stored auth) rather than an
    unauthenticated HTTP request, so issues in private repos can be read.
    GitHub's REST API returns 404 -- not 403 -- for issues the caller lacks
    access to, so on a 404 the error is worded to cover both "doesn't exist"
    and "not accessible with the current `gh` auth" rather than implying
    the issue is definitely missing.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{issue_id}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "404" in stderr:
            logger.error(
                f"Failed to fetch issue #{issue_id}: not found, or not accessible "
                f"with the current `gh` auth. If {owner}/{repo} is private, run "
                f"`gh auth status` to confirm the logged-in account has access. "
                f"({stderr})"
            )
        else:
            logger.error(f"Failed to fetch issue #{issue_id}: {stderr}")
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to fetch issue #{issue_id}: invalid JSON from `gh api`: {exc}")
        return None


def get_ollama_server_url(host: str = "localhost", port: int = 11434) -> str:
    """Get Ollama server url."""
    return f"http://{host}:{port}"


def is_ollama_running(host: str = "localhost", port: int = 11434) -> bool:
    """Check if Ollama is running locally."""
    try:
        host_url = get_ollama_server_url(host=host, port=port)
        resp = requests.get(f"{host_url}/api/tags", timeout=2)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def get_ollama_model() -> str:
    """Get Ollama model name from env, available models, or default."""
    # Check if explicitly set in env
    model = os.getenv("OLLAMA_MODEL")
    if model:
        return model

    # Try to get available models from Ollama
    try:
        ollama_url = get_ollama_server_url()
        resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            if models:
                # Prefer coder models, otherwise use first available
                for model in models:
                    name = model.get("name", "")
                    if "coder" in name.lower():
                        return name
                return models[0].get("name", "mistral")
    except requests.RequestException:
        pass

    return "mistral"


def _build_pr_body_prompt(issue_title: str, issue_body: str) -> str:
    """Build the shared PR-body generation prompt used by every provider."""
    return f"""Given this GitHub issue, generate a concise PR description with the following sections:

## What
Brief explanation of what was changed or implemented.

## Why
Why this change matters and what problem it solves.

## Testing
How the changes were tested.

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated if needed
- [ ] No breaking changes

Issue title: {issue_title}

Issue body:
{issue_body}

Generate only the sections above, no preamble."""


def generate_pr_body_with_ollama(issue_title: str, issue_body: str, model: str) -> Optional[str]:
    """Use Ollama to generate PR body sections."""
    prompt = _build_pr_body_prompt(issue_title, issue_body)

    ollama_url = get_ollama_server_url()
    logger.info(f"Waiting for Ollama ({model}) to generate the PR body, this can take up to 60s...")
    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "").strip()
    except requests.RequestException as exc:
        logger.error(f"Ollama generation failed: {exc}")
    return None


def get_lmstudio_server_url(host: str = "localhost", port: int = 1234) -> str:
    """Get LM Studio server url (base URL; the client appends `/v1/...`)."""
    return f"http://{host}:{port}"


def is_lmstudio_running(host: str = "localhost", port: int = 1234) -> bool:
    """Check if LM Studio is running locally with at least one model loaded.

    Requires a 200 from `/v1/models` AND a non-empty model list: an empty
    server is "not usable" just like Ollama being down, so callers fall back
    to the placeholder PR body rather than POSTing an empty model name.
    """
    try:
        host_url = get_lmstudio_server_url(host=host, port=port)
        resp = requests.get(f"{host_url}/v1/models", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return any(
                isinstance(m, dict) and m.get("id") for m in data.get("data", [])
            )
    except requests.RequestException:
        pass
    return False


def get_lmstudio_model() -> Optional[str]:
    """Get LM Studio model name from env, or auto-detect from loaded models.

    An explicit ``LMSTUDIO_MODEL`` wins; otherwise the first loaded model
    from `/v1/models` is used (preferring coder models, mirroring
    ``get_ollama_model``). Returns None -- never a made-up name -- when
    nothing is loaded, so the caller falls back to the placeholder body.
    """
    model = os.getenv("LMSTUDIO_MODEL")
    if model:
        return model

    try:
        lmstudio_url = get_lmstudio_server_url()
        resp = requests.get(f"{lmstudio_url}/v1/models", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            models = [
                m.get("id", "")
                for m in data.get("data", [])
                if isinstance(m, dict) and m.get("id")
            ]
            if models:
                for name in models:
                    if "coder" in name.lower():
                        return name
                return models[0]
    except requests.RequestException:
        pass
    return None


def generate_pr_body_with_lmstudio(issue_title: str, issue_body: str, model: str) -> Optional[str]:
    """Use LM Studio (OpenAI-compatible chat-completions) to generate PR body sections.

    Returns None on failure (mirroring ``generate_pr_body_with_ollama``) so
    the caller falls back to the placeholder PR body.
    """
    if not model:
        logger.warning("No LM Studio model provided; cannot generate PR body.")
        return None

    prompt = _build_pr_body_prompt(issue_title, issue_body)

    lmstudio_url = get_lmstudio_server_url()
    logger.info(f"Waiting for LM Studio ({model}) to generate the PR body, this can take up to 60s...")
    try:
        resp = requests.post(
            f"{lmstudio_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    except requests.RequestException as exc:
        logger.error(f"LM Studio generation failed: {exc}")
    return None


def _strip_issue_headings(text: str) -> str:
    """Remove markdown heading lines from an issue-body excerpt.

    Issue bodies in this repo use their own ``## What`` / ``## Why`` headings.
    Embedding such an excerpt raw inside a PR body section would render the
    issue's headings as nested PR sections (empty What/Why followed by a
    duplicate What), so heading lines are dropped before the excerpt is used.
    """
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def create_placeholder_pr_body(issue_id: int, issue_title: str, issue_body: str) -> str:
    """Create a placeholder PR body when Ollama is not available."""
    excerpt = _strip_issue_headings(issue_body)[:200] if issue_body else ""
    why = excerpt or "<!-- Explain why this change matters -->"
    return f"""## What
<!-- Describe what changed -->

## Why
{why}

## Testing
<!-- How was this tested? -->

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated if needed
- [ ] No breaking changes

Closes #{issue_id}"""


def find_existing_pr(owner: str, repo: str, branch: str) -> Optional[str]:
    """Return the URL of an existing open PR for this branch, if any."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "url",
            "-q",
            ".[0].url",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode == 0:
        url = result.stdout.strip()
        return url or None
    return None


def create_pr(
    owner: str,
    repo: str,
    branch: str,
    default_branch: str,
    title: str,
    body: str,
    draft: bool = False,
) -> Optional[str]:
    """Create a PR and return the URL, or the existing PR's URL if one is already open.

    ``draft=True`` passes ``--draft`` to ``gh pr create`` so the PR is not
    immediately visible/mergeable before a human review gate. Draft PRs are
    still included by ``find_existing_pr`` (``gh pr list --state open`` returns
    them), so a re-run returns the existing draft rather than duplicating it.
    """
    existing_pr_url = find_existing_pr(owner, repo, branch)
    if existing_pr_url:
        logger.info(f"PR already exists for branch '{branch}': {existing_pr_url}")
        return existing_pr_url

    body_file = None
    try:
        # Write body to temp file to avoid command-line quoting issues.
        # delete=False + explicit unlink (rather than delete=True) because an
        # open NamedTemporaryFile can't be reopened by the `gh` subprocess on
        # Windows while this process still holds the handle.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(body)
            body_file = Path(tmp.name)

        gh_pr_create = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body-file",
            str(body_file),
            "--head",
            branch,
            "--base",
            default_branch,
            "--repo",
            f"{owner}/{repo}",
        ]
        if draft:
            gh_pr_create.append("--draft")

        result = subprocess.run(
            gh_pr_create,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        if result.returncode == 0:
            match = re.search(r"https://github\.com/[^\s]+/pull/\d+", result.stdout)
            if match:
                return match.group(0)
            return result.stdout.strip()
        else:
            logger.error(f"Failed to create PR: {result.stderr}")
            return None
    except Exception as exc:
        logger.error(f"Error creating PR: {exc}")
        return None
    finally:
        if body_file:
            body_file.unlink(missing_ok=True)


def check_gh_available() -> None:
    """Verify gh CLI is installed and authenticated, exiting with a clear message if not."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            "GitHub CLI (gh) is not installed. Install from https://cli.github.com/"
        )
        sys.exit(1)

    if result.returncode != 0:
        logger.error(
            "GitHub CLI (gh) is not authenticated. Run 'gh auth login'."
        )
        sys.exit(1)


def get_llm_provider(provider_arg: Optional[str] = None) -> str:
    """Resolve the PR-body LLM provider: --provider, else LLM_PROVIDER env, else 'ollama'."""
    provider = provider_arg or os.getenv("LLM_PROVIDER", "ollama")
    if provider not in ("ollama", "lmstudio"):
        raise ValueError(
            f"Unsupported LLM provider: {provider!r} (choose 'ollama' or 'lmstudio')"
        )
    return provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a PR from the current branch")
    parser.add_argument(
        "--message",
        "-m",
        default=None,
        help="Commit message (default: 'Work on issue #NNNN')",
    )
    parser.add_argument(
        "--files",
        "-f",
        nargs="+",
        default=None,
        help="Specific files to commit (default: all changed files)",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "lmstudio"],
        default=None,
        help="LLM provider for PR-body generation (default: LLM_PROVIDER env var or 'ollama')",
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help=(
            "Skip LLM generation and use placeholder PR body "
            "(flag name kept for backward compatibility; applies to any provider)"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: OLLAMA_MODEL/LMSTUDIO_MODEL env var or auto-detected)",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create the PR as a draft (not immediately visible/mergeable)",
    )
    args = parser.parse_args()

    # Resolve the PR-body LLM provider (--provider > LLM_PROVIDER env > ollama).
    try:
        provider = get_llm_provider(args.provider)
    except ValueError as exc:
        logger.error(f"Error: {exc}")
        sys.exit(1)

    # Change to git root directory
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        git_root = result.stdout.strip()
        os.chdir(git_root)
    except subprocess.CalledProcessError:
        logger.error("Error: Could not determine git root directory")
        sys.exit(1)

    # Issue lookups go to the non-wiki repo (get_repo_info strips .wiki).
    # Branch and PR operations use the actual current repo.
    try:
        issue_owner, issue_repo = get_repo_info()
        actual_repo = get_actual_repo_name()
    except ValueError as exc:
        logger.error(f"Error: {exc}")
        sys.exit(1)

    owner = issue_owner
    repo = actual_repo
    logger.info(f"Issue from: {owner}/{issue_repo}")
    if repo != issue_repo:
        logger.info(f"PR target:  {owner}/{repo}")

    # Get current branch
    branch = get_current_branch()
    logger.info(f"Current branch: {branch}")

    # Extract issue ID
    issue_id = extract_issue_id(branch)
    if not issue_id:
        logger.error(f"Error: Could not extract issue ID from branch name '{branch}'")
        logger.error("Branch name should match pattern: fix/issue-NNNN-* or feat/issue-NNNN-*")
        sys.exit(1)

    logger.info(f"Issue ID: #{issue_id}")

    # Fetch issue
    logger.info(f"Fetching issue #{issue_id}...")
    issue = fetch_issue(issue_owner, issue_repo, issue_id)
    if not issue:
        sys.exit(1)

    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "")
    logger.info(f"Issue title: {issue_title}")

    # Get default branch
    default_branch = get_default_branch(owner, repo)
    logger.info(f"Target branch: {default_branch}")

    # Check if branch is ahead of main
    if not branch_is_ahead_of_main(branch=branch, default_branch=default_branch):
        logger.error(f"Error: Branch '{branch}' is not ahead of '{default_branch}'")
        sys.exit(1)

    # Stage and commit
    logger.info("Staging and committing changes...")
    if check_working_tree_clean():
        logger.info("Working tree is already clean. No new changes to commit.")
    else:
        commit_msg = args.message or f"Work on issue #{issue_id}"
        if stage_and_commit(args.files, commit_msg, branch, default_branch):
            logger.info(f"Committed: {commit_msg}")
        else:
            logger.info("No changes to commit, but continuing with PR creation...")

    # Push to remote
    logger.info("Pushing to remote...")
    if not push_to_remote(branch):
        sys.exit(1)

    # Generate PR body
    logger.info("Generating PR body...")
    pr_body = None
    if not args.no_ollama:
        if provider == "lmstudio":
            logger.info("Checking for LM Studio...")
            if is_lmstudio_running():
                logger.info("LM Studio is running. Generating PR body...")
                model = args.model or get_lmstudio_model()
                if not model:
                    logger.warning(
                        "LM Studio has no model loaded (set LMSTUDIO_MODEL or load a "
                        "model in LM Studio). Using placeholder PR body."
                    )
                else:
                    pr_body = generate_pr_body_with_lmstudio(issue_title, issue_body, model)
                    if pr_body:
                        logger.info("Generated PR body with LM Studio")
            else:
                logger.info("LM Studio not available. Using placeholder PR body.")
        else:
            logger.info("Checking for Ollama...")
            if is_ollama_running():
                logger.info("Ollama is running. Generating PR body...")
                model = args.model or get_ollama_model()
                pr_body = generate_pr_body_with_ollama(issue_title, issue_body, model)
                if pr_body:
                    logger.info("Generated PR body with Ollama")
            else:
                logger.info("Ollama not available. Using placeholder PR body.")

    if not pr_body:
        pr_body = create_placeholder_pr_body(issue_id, issue_title, issue_body)

    # Append Closes directive if not already present
    if f"Closes #{issue_id}" not in pr_body:
        pr_body += f"\n\nCloses #{issue_id}"

    # Create PR (wiki repos don't support PRs on GitHub)
    if is_wiki_repo():
        logger.info(
            "Skipping PR creation: %s/%s is a wiki repo (GitHub wiki repos "
            "don't support pull requests). Changes have been pushed to the "
            "branch.",
            owner,
            repo,
        )
        logger.info("\n[OK] Branch '%s' pushed to %s/%s", branch, owner, repo)
        return

    check_gh_available()
    logger.info("Creating PR...")
    pr_url = create_pr(
        owner,
        repo,
        branch,
        default_branch,
        f"[Issue #{issue_id}] {issue_title}",
        pr_body,
        draft=args.draft,
    )

    if pr_url:
        logger.info("\n✓ PR created successfully!")
        logger.info(f"  {pr_url}")
    else:
        logger.error("Failed to create PR")
        sys.exit(1)


if __name__ == "__main__":
    main()
