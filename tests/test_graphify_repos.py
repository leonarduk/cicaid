import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cicaid_devtools import graphify_repos


def _config(text: str, tmp_path: Path) -> Path:
    path = tmp_path / ".cicaid-graphify.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_repos_parses_valid_config(tmp_path):
    path = _config(
        """
        [[repos]]
        name = "allotmint"
        url = "https://github.com/leonarduk/allotmint"
        extract = true

        [[repos]]
        name = "cicaid"
        url = "https://github.com/leonarduk/cicaid"
        """,
        tmp_path,
    )
    repos = graphify_repos.load_repos(path)
    assert repos == (
        graphify_repos.RepoTarget(
            "allotmint", "https://github.com/leonarduk/allotmint", extract=True
        ),
        graphify_repos.RepoTarget("cicaid", "https://github.com/leonarduk/cicaid", extract=False),
    )


def test_load_repos_missing_config_raises(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        graphify_repos.load_repos(tmp_path / "nope.toml")


def test_load_repos_empty_repos_list_raises(tmp_path):
    path = _config("repos = []\n", tmp_path)
    with pytest.raises(SystemExit, match="no \\[\\[repos\\]\\]"):
        graphify_repos.load_repos(path)


def test_load_repos_missing_required_key_raises(tmp_path):
    path = _config('[[repos]]\nname = "allotmint"\n', tmp_path)
    with pytest.raises(SystemExit, match="missing required key"):
        graphify_repos.load_repos(path)


def test_ensure_checkout_clones_when_missing(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://github.com/leonarduk/cicaid")
    workdir = tmp_path / "work"

    with patch.object(graphify_repos.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0)
        result = graphify_repos.ensure_checkout(repo, workdir)

    run.assert_called_once_with(
        ["git", "clone", "--depth", "1", "--", repo.url, str(workdir / "cicaid")],
        check=True,
    )
    assert result == workdir / "cicaid"


def test_ensure_checkout_fetches_and_resets_when_present(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://github.com/leonarduk/cicaid")
    workdir = tmp_path / "work"
    repo_dir = workdir / "cicaid"
    (repo_dir / ".git").mkdir(parents=True)

    symbolic_ref_result = MagicMock(returncode=0, stdout="refs/remotes/origin/main\n")

    with patch.object(graphify_repos.subprocess, "run") as run:
        run.side_effect = [
            MagicMock(returncode=0),  # git remote set-url
            MagicMock(returncode=0),  # git fetch
            symbolic_ref_result,  # git symbolic-ref
            MagicMock(returncode=0),  # git checkout
            MagicMock(returncode=0),  # git reset --hard
        ]
        result = graphify_repos.ensure_checkout(repo, workdir)

    assert result == repo_dir
    calls = [call.args[0] for call in run.call_args_list]
    assert calls[0] == ["git", "remote", "set-url", "--", "origin", repo.url]
    assert calls[1] == ["git", "fetch", "--depth", "1", "origin"]
    assert calls[3] == ["git", "checkout", "main"]
    assert calls[4] == ["git", "reset", "--hard", "origin/main"]


def test_ensure_checkout_removes_stale_graphify_out_on_refresh(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://github.com/leonarduk/cicaid")
    workdir = tmp_path / "work"
    repo_dir = workdir / "cicaid"
    (repo_dir / ".git").mkdir(parents=True)
    stale_out = repo_dir / "graphify-out"
    stale_out.mkdir()
    (stale_out / "graph.json").write_text("{}", encoding="utf-8")

    symbolic_ref_result = MagicMock(returncode=0, stdout="refs/remotes/origin/main\n")
    with patch.object(graphify_repos.subprocess, "run") as run:
        run.side_effect = [
            MagicMock(returncode=0),  # git remote set-url
            MagicMock(returncode=0),  # git fetch
            symbolic_ref_result,  # git symbolic-ref
            MagicMock(returncode=0),  # git checkout
            MagicMock(returncode=0),  # git reset --hard
        ]
        graphify_repos.ensure_checkout(repo, workdir)

    assert not stale_out.exists()


def test_parse_config_rejects_non_table_entry():
    with pytest.raises(SystemExit, match="must be a table"):
        graphify_repos._parse_config('repos = ["not-a-table"]\n', "config.toml")


def test_parse_config_rejects_non_string_name():
    text = '[[repos]]\nname = 5\nurl = "https://example.com/x"\n'
    with pytest.raises(SystemExit, match="name must be a non-empty string"):
        graphify_repos._parse_config(text, "config.toml")


def test_parse_config_rejects_path_traversal_name():
    text = '[[repos]]\nname = "../escape"\nurl = "https://example.com/x"\n'
    with pytest.raises(SystemExit, match="single path component"):
        graphify_repos._parse_config(text, "config.toml")


def test_parse_config_rejects_slash_in_name():
    text = '[[repos]]\nname = "sub/dir"\nurl = "https://example.com/x"\n'
    with pytest.raises(SystemExit, match="single path component"):
        graphify_repos._parse_config(text, "config.toml")


def test_parse_config_rejects_duplicate_names():
    text = (
        '[[repos]]\nname = "cicaid"\nurl = "https://example.com/a"\n\n'
        '[[repos]]\nname = "cicaid"\nurl = "https://example.com/b"\n'
    )
    with pytest.raises(SystemExit, match="duplicate repo name"):
        graphify_repos._parse_config(text, "config.toml")


def test_run_graphify_raises_when_binary_missing(tmp_path):
    with patch.object(graphify_repos.shutil, "which", return_value=None):
        with pytest.raises(SystemExit, match="graphify"):
            graphify_repos.run_graphify(tmp_path, extract=False, dry_run=False)


def test_run_graphify_dry_run_does_not_execute(tmp_path):
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            assert graphify_repos.run_graphify(tmp_path, extract=True, dry_run=True) is True

    run.assert_not_called()


def _clear_api_keys(monkeypatch):
    for var in graphify_repos.API_KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_run_graphify_omits_code_only_with_api_key_and_extract(tmp_path, monkeypatch):
    _clear_api_keys(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0)
            assert graphify_repos.run_graphify(tmp_path, extract=True, dry_run=False) is True

    run.assert_called_once_with(["graphify", "."], cwd=tmp_path, check=False)


def test_run_graphify_falls_back_to_code_only_without_api_key(tmp_path, monkeypatch):
    _clear_api_keys(monkeypatch)
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0)
            assert graphify_repos.run_graphify(tmp_path, extract=True, dry_run=False) is True

    run.assert_called_once_with(["graphify", ".", "--code-only"], cwd=tmp_path, check=False)


def test_run_graphify_uses_code_only_when_extract_not_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0)
            assert graphify_repos.run_graphify(tmp_path, extract=False, dry_run=False) is True

    run.assert_called_once_with(["graphify", ".", "--code-only"], cwd=tmp_path, check=False)


def test_run_graphify_returns_false_on_failure(tmp_path):
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=1)
            assert graphify_repos.run_graphify(tmp_path, extract=False, dry_run=False) is False


def test_run_graphify_dry_run_skips_which_check(tmp_path):
    with patch.object(graphify_repos.shutil, "which") as which:
        with patch.object(graphify_repos.subprocess, "run") as run:
            assert graphify_repos.run_graphify(tmp_path, extract=False, dry_run=True) is True

    which.assert_not_called()
    run.assert_not_called()


def test_collect_output_warns_when_nothing_found(tmp_path, capsys):
    repo = graphify_repos.RepoTarget("cicaid", "https://example.com/cicaid")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    out_root = tmp_path / "out"

    graphify_repos.collect_output(repo, repo_dir, out_root)

    assert "no known graphify output files found" in capsys.readouterr().err.lower()


def test_collect_output_copies_only_existing_files(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://example.com/cicaid")
    repo_dir = tmp_path / "repo"
    (repo_dir / "graphify-out").mkdir(parents=True)
    (repo_dir / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    out_root = tmp_path / "out"

    graphify_repos.collect_output(repo, repo_dir, out_root)

    assert (out_root / "cicaid" / "graph.json").read_text(encoding="utf-8") == "{}"
    assert not (out_root / "cicaid" / "manifest.json").exists()


def test_select_repos_rejects_unknown_name():
    repos = (graphify_repos.RepoTarget("cicaid", "https://example.com/cicaid"),)
    args = MagicMock(all=False, repo=["nope"])
    with pytest.raises(SystemExit, match="Unknown repo"):
        graphify_repos.select_repos(args, repos)


def test_select_repos_returns_all_when_flag_set():
    repos = (
        graphify_repos.RepoTarget("a", "https://example.com/a"),
        graphify_repos.RepoTarget("b", "https://example.com/b"),
    )
    args = MagicMock(all=True, repo=None)
    assert graphify_repos.select_repos(args, repos) == list(repos)


def test_select_repos_filters_by_name():
    repos = (
        graphify_repos.RepoTarget("a", "https://example.com/a"),
        graphify_repos.RepoTarget("b", "https://example.com/b"),
    )
    args = MagicMock(all=False, repo=["b"])
    assert graphify_repos.select_repos(args, repos) == [repos[1]]


def test_process_repo_dry_run_does_not_touch_filesystem(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://example.com/cicaid")
    with patch.object(graphify_repos.shutil, "which", return_value="/usr/bin/graphify"):
        with patch.object(graphify_repos.subprocess, "run") as run:
            result = graphify_repos.process_repo(
                repo, tmp_path / "work", tmp_path / "out", dry_run=True
            )
            assert result

    run.assert_not_called()


def test_process_repo_reports_checkout_failure(tmp_path):
    repo = graphify_repos.RepoTarget("cicaid", "https://example.com/cicaid")
    with patch.object(
        graphify_repos,
        "ensure_checkout",
        side_effect=subprocess.CalledProcessError(1, ["git", "clone"]),
    ):
        result = graphify_repos.process_repo(
            repo, tmp_path / "work", tmp_path / "out", dry_run=False
        )
        assert not result
