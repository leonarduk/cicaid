import pytest

from cicaid_devtools import onboard_issue_worm
from cicaid_devtools.onboard_issue_worm import (
    CHECKS_TOML_STUB,
    detect_checks_config,
    ensure_checks_config,
    ensure_gitignore_entries,
    main,
    render_workflow,
    worm_pat_instructions,
)


def test_render_workflow_hosted_local_has_no_cloud_env():
    content = render_workflow("ubuntu-latest", "v1", "local")
    assert "runs-on: ubuntu-latest" in content
    assert "leonarduk/issue-worm@v1" in content
    assert "CODER_MODEL_SOURCE" not in content


def test_render_workflow_cloud_adds_env_block():
    content = render_workflow("ubuntu-latest", "v1", "cloud")
    assert "CODER_MODEL_SOURCE: cloud" in content
    assert "DEEPSEEK_API_KEY" in content


def test_render_workflow_self_hosted_runner_label():
    content = render_workflow("[self-hosted, linux, x64]", "v1", "local")
    assert "runs-on: [self-hosted, linux, x64]" in content


def test_ensure_gitignore_entries_creates_file(tmp_path):
    added = ensure_gitignore_entries(tmp_path)
    assert added == [".issue-worm/", ".issue-worm-workspace/"]
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".issue-worm/" in content
    assert ".issue-worm-workspace/" in content


def test_ensure_gitignore_entries_idempotent(tmp_path):
    ensure_gitignore_entries(tmp_path)
    added_again = ensure_gitignore_entries(tmp_path)
    assert added_again == []


def test_ensure_gitignore_entries_appends_to_existing_content(tmp_path):
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    ensure_gitignore_entries(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__/" in content
    assert ".issue-worm/" in content


def test_ensure_gitignore_entries_dry_run_does_not_write(tmp_path):
    added = ensure_gitignore_entries(tmp_path, dry_run=True)
    assert added == [".issue-worm/", ".issue-worm-workspace/"]
    assert not (tmp_path / ".gitignore").exists()


def test_detect_checks_config_pytest_testpaths(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8"
    )
    detected = detect_checks_config(tmp_path)
    assert detected is not None
    assert "pytest tests -q" in detected


def test_detect_checks_config_pytest_uses_uv_when_lockfile_present(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["backend/tests"]\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    detected = detect_checks_config(tmp_path)
    assert "uv run pytest backend/tests -q" in detected


def test_detect_checks_config_npm_test_script(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest run"}}', encoding="utf-8"
    )
    detected = detect_checks_config(tmp_path)
    assert detected is not None
    assert "npm test" in detected


def test_detect_checks_config_returns_none_when_unclear(tmp_path):
    assert detect_checks_config(tmp_path) is None


def test_ensure_checks_config_writes_stub_when_undetectable(tmp_path):
    written = ensure_checks_config(tmp_path)
    assert written == CHECKS_TOML_STUB
    assert (tmp_path / ".cicaid-checks.toml").read_text(encoding="utf-8") == CHECKS_TOML_STUB


def test_ensure_checks_config_leaves_existing_file_alone(tmp_path):
    (tmp_path / ".cicaid-checks.toml").write_text("# already here\n", encoding="utf-8")
    written = ensure_checks_config(tmp_path)
    assert written is None
    assert (tmp_path / ".cicaid-checks.toml").read_text(encoding="utf-8") == "# already here\n"


def test_ensure_checks_config_dry_run_does_not_write(tmp_path):
    written = ensure_checks_config(tmp_path, dry_run=True)
    assert written == CHECKS_TOML_STUB
    assert not (tmp_path / ".cicaid-checks.toml").exists()


# --- the printed WORM_PAT recipe (#48) ---------------------------------------


def test_worm_pat_instructions_say_what_to_grant_and_where_to_paste_it():
    text = worm_pat_instructions("acme", "widget")

    # The things a reader can't proceed without, and the one people get
    # wrong (issue-worm's README: `issues: read` fails first, and
    # GITHUB_TOKEN looks like it should work).
    assert "https://github.com/settings/personal-access-tokens/new" in text
    assert "https://github.com/acme/widget/settings/secrets/actions/new" in text
    for permission in ("Contents", "Pull requests", "Issues"):
        assert permission in text
    assert "GITHUB_TOKEN" in text
    assert "issues: read" in text
    # The owner to pick as the token's resource owner, not the whole slug.
    assert "Resource owner:\n       acme\n" in text
    # The coarser fallback, for someone who only has classic tokens.
    assert "https://github.com/settings/tokens/new" in text
    assert "`repo` scope" in text


def test_worm_pat_instructions_stay_readable_in_a_terminal():
    # A long slug, because only the two URL lines may grow with it -- prose
    # that interpolates the repo name would start wrapping in an 80-column
    # shell on a repo like this one.
    text = worm_pat_instructions("a-fairly-long-org-name", "and-its-longer-repo")

    lines = [line for line in text.splitlines() if "https://" not in line]
    # Terminal output, not a PR body: no markdown tables, and narrow enough
    # not to wrap in an 80-column shell.
    assert not any(line.lstrip().startswith("|") for line in lines)
    assert not any(line.lstrip().startswith("#") for line in lines)
    too_wide = [line for line in lines if len(line) > 80]
    assert not too_wide, too_wide
    # Short enough that it doesn't scroll a reminder off the screen.
    assert len(lines) < 50
    # The module writes `--` rather than en/em dashes throughout.
    assert not any(dash in text for dash in ("\u2013", "\u2014"))


def _onboard(tmp_path, monkeypatch, *args, repo_info=("acme", "widget")):
    """Run main() against tmp_path, with the git/gh reach-out stubbed."""
    monkeypatch.setattr(onboard_issue_worm, "get_repo_root", lambda: str(tmp_path))

    def fake_repo_info():
        if isinstance(repo_info, Exception):
            raise repo_info
        return repo_info

    monkeypatch.setattr(onboard_issue_worm, "get_repo_info", fake_repo_info)
    monkeypatch.setattr(onboard_issue_worm, "ensure_labels", lambda *a, **k: ["issue-worm"])
    return main(["--dry-run", *args])


def test_main_prints_the_recipe_for_this_repo(tmp_path, monkeypatch, capsys):
    assert _onboard(tmp_path, monkeypatch) == 0

    out = capsys.readouterr().out
    # The reminder shrinks to a pointer, and the recipe itself follows.
    assert "Create the WORM_PAT repo secret -- step-by-step recipe below." in out
    assert worm_pat_instructions("acme", "widget") in out


def test_main_falls_back_to_placeholders_when_the_remote_is_unreadable(
    tmp_path, monkeypatch, capsys
):
    # --skip-labels is the one mode that doesn't need to reach the repo, so a
    # checkout without a usable origin still gets its recipe -- with a slug
    # the reader substitutes -- rather than a traceback.
    assert (
        _onboard(
            tmp_path,
            monkeypatch,
            "--skip-labels",
            repo_info=ValueError("no origin"),
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "https://github.com/<owner>/<name>/settings/secrets/actions/new" in out


def test_main_still_fails_on_an_unreadable_remote_when_it_must_label(tmp_path, monkeypatch):
    # Creating the labels does need the real slug: don't paper that over.
    with pytest.raises(ValueError):
        _onboard(tmp_path, monkeypatch, repo_info=ValueError("no origin"))
