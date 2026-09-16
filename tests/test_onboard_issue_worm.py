from cicaid_devtools.onboard_issue_worm import (
    CHECKS_TOML_STUB,
    detect_checks_config,
    ensure_checks_config,
    ensure_gitignore_entries,
    render_workflow,
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
