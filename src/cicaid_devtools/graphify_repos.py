"""Orchestrate graphify knowledge-graph runs across multiple repos.

Graphify (https://pypi.org/project/graphifyy/) is a codebase knowledge-graph
generator invoked per-repo (`graphify .`); today it only runs standalone
inside each repo's own GitHub Actions workflow (see e.g. allotmint's
`.github/workflows/graphify.yml`). This module adds a local orchestrator that
clones/refreshes a configured list of repos, runs graphify in each, and
collects the results into one combined output directory -- so a user can
regenerate the graph for every repo they care about with a single command
instead of maintaining a copy of that workflow in each repo.

Repos are listed in a `.cicaid-graphify.toml` file (see load_repos() for the
expected shape). Each repo is cloned into a local working directory on first
run and fetched + fast-forwarded on subsequent runs, then `graphify .` runs
with that checkout as the working directory. `graphify .` semantically
extracts every doc/paper/image file in the corpus by default, which fails
outright without a supported LLM API key set in the environment -- so a
repo's `extract` config flag only enables that (by omitting graphify's
`--code-only` flag) when one of the API key env vars graphify auto-detects
is actually set; otherwise the always-safe, key-free code-only scan runs
instead (see run_graphify()). The known output files graphify writes to
`graphify-out/` are then copied into `<out>/<repo-name>/`.

This deliberately does not attempt to publish anywhere beyond the local
output directory (no scheduling, no cross-repo PR automation) -- that's a
natural follow-up once the config format and orchestration here have proven
out, not a requirement for the first version.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from interactive import is_interactive  # noqa: E402

CONFIG_FILENAME = ".cicaid-graphify.toml"
DEFAULT_WORKDIR = Path(".cicaid-graphify") / "repos"
DEFAULT_OUTDIR = Path("graphify-combined")

GRAPHIFY_BINARY = "graphify"
GRAPHIFY_OUTPUT_FILES = ("graph.json", "manifest.json", ".graphify_analysis.json")

# Env vars graphify auto-detects a backend from, in the order its own --help
# lists them (gemini, kimi, claude, openai, deepseek).
API_KEY_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)


@dataclass(frozen=True)
class RepoTarget:
    """A single repo to run graphify against."""

    name: str
    url: str
    extract: bool = False


def _parse_config(text: str, source: str) -> tuple[RepoTarget, ...]:
    """Parse a .cicaid-graphify.toml document into RepoTarget objects.

    Expected shape:
        [[repos]]
        name = "allotmint"
        url = "https://github.com/leonarduk/allotmint"
        extract = true

        [[repos]]
        name = "cicaid"
        url = "https://github.com/leonarduk/cicaid"
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"Failed to parse {source}: {exc}") from exc

    entries = data.get("repos")
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"{source} has no [[repos]] entries.")

    repos = []
    seen_names = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SystemExit(f"{source}: repos[{index}] must be a table, got {entry!r}")
        try:
            name = entry["name"]
            url = entry["url"]
        except KeyError as exc:
            raise SystemExit(f"{source}: repos[{index}] is missing required key {exc}") from exc
        if not isinstance(name, str) or not name:
            raise SystemExit(f"{source}: repos[{index}].name must be a non-empty string")
        if not isinstance(url, str) or not url:
            raise SystemExit(f"{source}: repos[{index}].url must be a non-empty string")
        if name != Path(name).name or name in (".", ".."):
            raise SystemExit(
                f"{source}: repos[{index}].name {name!r} must be a single path component "
                "(no '/', '\\', or '..')"
            )
        if name in seen_names:
            raise SystemExit(f"{source}: duplicate repo name {name!r}")
        seen_names.add(name)
        repos.append(RepoTarget(name=name, url=url, extract=bool(entry.get("extract", False))))
    return tuple(repos)


def load_repos(config_path: Path) -> tuple[RepoTarget, ...]:
    """Load the repo list from a .cicaid-graphify.toml file.

    Unlike run-ci-checks' config, there is no sensible default repo list --
    this feature is meaningless without the user's own list of repos -- so a
    missing config is always an error.
    """
    if not config_path.exists():
        raise SystemExit(
            f"{config_path} not found. Create it with a [[repos]] list "
            "(see cicaid_devtools.graphify_repos module docstring for the format)."
        )
    return _parse_config(config_path.read_text(encoding="utf-8"), str(config_path))


def ensure_checkout(repo: RepoTarget, workdir: Path) -> Path:
    """Clone `repo` into `workdir` if missing, else fetch and fast-forward it.

    Returns the local checkout path. Uses a shallow clone / fetch since only
    the current state of each repo is needed, not history. An existing
    checkout has its `origin` URL re-pointed to `repo.url` first, in case
    the config changed since the last run. A prior run's own `graphify-out/`
    (gitignored, so `git reset --hard` alone wouldn't touch it) is removed
    so collect_output() never copies stale artifacts left over from a run
    that wrote fewer files than before -- only that directory is removed,
    not every gitignored path, so other gitignored build artifacts (a
    node_modules/, a .venv/) aren't needlessly wiped on every refresh.
    """
    repo_dir = workdir / repo.name
    if not (repo_dir / ".git").exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--", repo.url, str(repo_dir)],
            check=True,
        )
        return repo_dir

    subprocess.run(["git", "remote", "set-url", "--", "origin", repo.url], cwd=repo_dir, check=True)
    subprocess.run(["git", "fetch", "--depth", "1", "origin"], cwd=repo_dir, check=True)
    head = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    branch = head.removeprefix("refs/remotes/origin/")
    subprocess.run(["git", "checkout", branch], cwd=repo_dir, check=True)
    subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=repo_dir, check=True)
    shutil.rmtree(repo_dir / "graphify-out", ignore_errors=True)
    return repo_dir


def run_graphify(repo_dir: Path, extract: bool, dry_run: bool) -> bool:
    """Run `graphify .` in `repo_dir`.

    `graphify .` semantically extracts every doc/paper/image file in the
    corpus by default, which fails outright if no supported LLM API key is
    set (verified against a real run: it errors with "no LLM API key
    found ... or pass --code-only"). So this only omits `--code-only` (i.e.
    only asks for full semantic extraction) when `extract` is requested AND
    one of the API key env vars graphify auto-detects is actually set;
    otherwise it runs the always-safe, key-free code-only scan.

    Returns True on success (or in dry-run mode, where nothing is executed).
    """
    use_semantic_extraction = extract and any(os.environ.get(var) for var in API_KEY_ENV_VARS)
    args = (
        [GRAPHIFY_BINARY, "."] if use_semantic_extraction else [GRAPHIFY_BINARY, ".", "--code-only"]
    )

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}$ {' '.join(args)} (in {repo_dir})")
    if extract and not use_semantic_extraction:
        print(
            f"{prefix}  note: --extract requested for this repo but no supported API key "
            f"({', '.join(API_KEY_ENV_VARS)}) is set -- falling back to --code-only"
        )
    if dry_run:
        return True

    if shutil.which(GRAPHIFY_BINARY) is None:
        raise SystemExit(
            f"'{GRAPHIFY_BINARY}' is not installed or not on PATH. "
            "Install it with `pip install graphifyy` first."
        )

    result = subprocess.run(args, cwd=repo_dir, check=False)
    return result.returncode == 0


def collect_output(repo: RepoTarget, repo_dir: Path, out_root: Path) -> None:
    """Copy graphify's known output files for `repo` into `out_root/<repo.name>/`.

    Warns (rather than failing outright) when none of the known files were
    found -- process_repo() still reports the repo as a success since
    graphify itself exited 0, but silently writing an empty output
    directory with no diagnostic at all would hide a real problem.
    """
    src = repo_dir / "graphify-out"
    dest = out_root / repo.name
    dest.mkdir(parents=True, exist_ok=True)
    copied_any = False
    for filename in GRAPHIFY_OUTPUT_FILES:
        source_file = src / filename
        if source_file.exists():
            shutil.copy2(source_file, dest / filename)
            copied_any = True
    if not copied_any:
        print(
            f"WARNING: no known graphify output files found in {src} for {repo.name}",
            file=sys.stderr,
        )


def process_repo(repo: RepoTarget, workdir: Path, out_root: Path, dry_run: bool) -> bool:
    """Refresh, run graphify for, and collect output from a single repo.

    Returns False only when a real failure occurred; dry-run always returns
    True since nothing is actually executed.
    """
    print(f"\n== {repo.name} ({repo.url}) ==")
    if dry_run:
        print(f"[DRY RUN] would clone/refresh {repo.url} into {workdir / repo.name}")
        return run_graphify(workdir / repo.name, repo.extract, dry_run=True)

    try:
        repo_dir = ensure_checkout(repo, workdir)
    except subprocess.CalledProcessError as exc:
        print(f"FAILED to check out {repo.name}: {exc}", file=sys.stderr)
        return False

    if not run_graphify(repo_dir, repo.extract, dry_run=False):
        print(f"FAILED: graphify . in {repo.name}", file=sys.stderr)
        return False

    collect_output(repo, repo_dir, out_root)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Run graphify across a configured list of repos.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--repo", action="append", help="repo to process (by name); repeatable")
    selection.add_argument("--all", action="store_true", help="process every configured repo")
    selection.add_argument("--list", action="store_true", help="list configured repos and exit")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(CONFIG_FILENAME),
        help=f"path to a repo-list config (default: ./{CONFIG_FILENAME})",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help=f"directory to clone/refresh repo checkouts in (default: {DEFAULT_WORKDIR})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTDIR,
        help=f"directory to collect combined graphify output in (default: {DEFAULT_OUTDIR})",
    )
    parser.add_argument("--dry-run", action="store_true", help="print actions without running them")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed repo")
    return parser.parse_args(argv)


def select_repos(args: argparse.Namespace, repos: tuple[RepoTarget, ...]) -> list[RepoTarget]:
    """Resolve flags to the repos that should be processed."""
    if args.all:
        return list(repos)
    if args.repo:
        valid_names = {repo.name for repo in repos}
        unknown = [name for name in args.repo if name not in valid_names]
        if unknown:
            raise SystemExit(
                f"Unknown repo(s): {', '.join(unknown)}. "
                f"Configured: {', '.join(sorted(valid_names))}"
            )
        selected = set(args.repo)
        return [repo for repo in repos if repo.name in selected]
    if not is_interactive(require_stdout=False):
        raise SystemExit("No repo selected. Use --repo NAME, --all, or --list.")
    print_repos(repos)
    answer = input("Select repos by number (comma-separated), or 'all': ").strip().lower()
    if answer == "all":
        return list(repos)
    try:
        indexes = [int(value.strip()) for value in answer.split(",")]
        if not indexes or any(index < 1 or index > len(repos) for index in indexes):
            raise ValueError
    except ValueError as exc:
        raise SystemExit("Invalid selection; use listed numbers or 'all'.") from exc
    return [repos[index - 1] for index in dict.fromkeys(indexes)]


def print_repos(repos: tuple[RepoTarget, ...]) -> None:
    """Print the configured repos."""
    for index, repo in enumerate(repos, start=1):
        extract_note = " (+ semantic extraction, if a key is set)" if repo.extract else ""
        print(f"{index}. {repo.name}: {repo.url}{extract_note}")


def main(argv: list[str] | None = None) -> int:
    """Provide the CLI entry point."""
    args = parse_args(argv)
    repos = load_repos(args.config)
    if args.list:
        print_repos(repos)
        return 0

    selected = select_repos(args, repos)
    had_failures = False
    for repo in selected:
        if not process_repo(repo, args.workdir, args.out, args.dry_run):
            had_failures = True
            if not args.keep_going:
                return 1

    return 1 if had_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
