import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from cicaid_devtools import setup_review_actions as sra

# ──────────────────────── get_cicaid_pro_install_spec ──────────────────────


def test_get_cicaid_pro_install_spec_uses_pinned_ref():
    spec = sra.get_cicaid_pro_install_spec()

    assert spec == (
        f"cicaid-devtools @ git+https://github.com/leonarduk/cicaid-pro.git@{sra.CICAID_PRO_REF}"
    )


def test_get_cicaid_pro_install_spec_accepts_ref_override():
    spec = sra.get_cicaid_pro_install_spec(ref="v1.2.3")

    assert spec == "cicaid-devtools @ git+https://github.com/leonarduk/cicaid-pro.git@v1.2.3"


# ───────────────────────── prompt_yes_no / prompt_text ──────────────────────


def test_prompt_yes_no_returns_default_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: False)
    assert sra.prompt_yes_no("Enable X?", default=True) is True
    assert sra.prompt_yes_no("Enable X?", default=False) is False


def test_prompt_yes_no_accepts_yes_and_no(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: True)

    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert sra.prompt_yes_no("Enable X?", default=False) is True

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert sra.prompt_yes_no("Enable X?", default=True) is False


def test_prompt_yes_no_empty_answer_uses_default(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert sra.prompt_yes_no("Enable X?", default=True) is True


def test_prompt_yes_no_eof_uses_default(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: True)

    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert sra.prompt_yes_no("Enable X?", default=True) is True


def test_prompt_text_returns_default_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: False)
    assert sra.prompt_text("Language?", default="python") == "python"


def test_prompt_text_returns_typed_answer(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "java")
    assert sra.prompt_text("Language?", default="python") == "java"


def test_prompt_text_empty_answer_uses_default(monkeypatch):
    monkeypatch.setattr(sra.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert sra.prompt_text("Language?", default="python") == "python"


# ───────────────────────── ensure_dependency_graph_enabled ──────────────────


def test_ensure_dependency_graph_already_enabled_skips_put(caplog):
    caplog.set_level("INFO")
    with patch.object(sra.requests, "get") as mock_get, patch.object(
        sra.requests, "put"
    ) as mock_put:
        mock_get.return_value = MagicMock(status_code=204)

        sra.ensure_dependency_graph_enabled("owner", "repo", "token")

        mock_put.assert_not_called()
        assert "already enabled" in caplog.text


def test_ensure_dependency_graph_enables_when_missing(caplog):
    caplog.set_level("INFO")
    with patch.object(sra.requests, "get") as mock_get, patch.object(
        sra.requests, "put"
    ) as mock_put:
        mock_get.return_value = MagicMock(status_code=404)
        mock_put.return_value = MagicMock(status_code=204)

        sra.ensure_dependency_graph_enabled("owner", "repo", "token")

        mock_put.assert_called_once()
        assert "Enabled the dependency graph" in caplog.text


def test_ensure_dependency_graph_warns_without_raising_on_put_failure(caplog):
    with patch.object(sra.requests, "get") as mock_get, patch.object(
        sra.requests, "put"
    ) as mock_put:
        mock_get.return_value = MagicMock(status_code=404)
        mock_put.return_value = MagicMock(status_code=403)

        sra.ensure_dependency_graph_enabled("owner", "repo", "token")  # must not raise

        assert "Could not enable the dependency graph automatically" in caplog.text
        assert "settings/security_analysis" in caplog.text


def test_ensure_dependency_graph_warns_without_raising_on_request_exception(caplog):
    import requests as req

    with patch.object(sra.requests, "get") as mock_get:
        mock_get.side_effect = req.ConnectionError("network down")

        sra.ensure_dependency_graph_enabled("owner", "repo", "token")  # must not raise

        assert "Could not check/enable the dependency graph" in caplog.text


# ─────────────────────── ensure_default_branch_ruleset ─────────────────────


def test_ensure_default_branch_ruleset_creates_ruleset():
    with patch.object(sra.requests, "get") as mock_get, patch.object(
        sra.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = []
        mock_post.return_value = MagicMock(status_code=201)

        assert sra.ensure_default_branch_ruleset("owner", "repo", "token") is True

        payload = mock_post.call_args.kwargs["json"]
        assert payload["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
        assert {rule["type"] for rule in payload["rules"]} == {
            "deletion",
            "non_fast_forward",
            "pull_request",
        }


def test_ensure_default_branch_ruleset_updates_matching_ruleset():
    with patch.object(sra.requests, "get") as mock_get, patch.object(
        sra.requests, "put"
    ) as mock_put, patch.object(sra.requests, "post") as mock_post:
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = [
            {"id": 42, "name": sra.DEFAULT_BRANCH_RULESET_NAME}
        ]
        mock_put.return_value = MagicMock(status_code=200)

        assert sra.ensure_default_branch_ruleset("owner", "repo", "token") is True

        assert mock_put.call_args.args[0].endswith("/rulesets/42")
        mock_post.assert_not_called()


def test_ensure_default_branch_ruleset_reports_api_failure(caplog):
    import requests as req

    with patch.object(sra.requests, "get", side_effect=req.ConnectionError("offline")):
        assert sra.ensure_default_branch_ruleset("owner", "repo", "token") is False
    assert "Could not configure default-branch protection" in caplog.text


# ──────────────────────────── render_workflows ──────────────────────────────


def test_render_workflows_includes_reusable_provider_and_extras_by_default():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek", "gpt"])

    assert set(files) == {
        ".github/workflows/_ai-pr-review.yml",
        ".github/scripts/pip_install_cicaid_pro.sh",
        ".github/workflows/deepseek-pr-review.yml",
        ".github/workflows/gpt-pr-review.yml",
        ".github/workflows/dependency-review.yml",
        ".github/workflows/workflow-lint.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/pr-lint.yml",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.md",
    }


def test_render_workflows_substitutes_install_spec():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])

    reusable = files[".github/workflows/_ai-pr-review.yml"]
    assert 'pip_install_cicaid_pro.sh pip install --retries 10 "cicaid-devtools @ some-url"' in reusable
    assert sra.INSTALL_SPEC_PLACEHOLDER not in reusable


def test_render_workflows_includes_cicaid_pro_install_script():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])

    script = files[".github/scripts/pip_install_cicaid_pro.sh"]
    assert "CICAID_PRO_TOKEN" in script
    assert "leonarduk/cicaid-pro" in script


def test_render_workflows_threads_cicaid_pro_token_secret():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek", "gpt"])

    reusable = files[".github/workflows/_ai-pr-review.yml"]
    assert "cicaid_pro_token:" in reusable

    for provider in ("deepseek", "gpt"):
        caller = files[f".github/workflows/{provider}-pr-review.yml"]
        assert "cicaid_pro_token: ${{ secrets.CICAID_PRO_TOKEN }}" in caller


def test_render_workflows_linked_issue_extraction_drops_refs():
    """Issue #409: the installed workflow must not treat Refs #N as the
    linked issue -- extraction goes through cicaid_devtools.lib.linked_issue.
    """
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])

    reusable = files[".github/workflows/_ai-pr-review.yml"]
    assert "python3 -m cicaid_devtools.lib.linked_issue" in reusable
    assert "(Closes|Fixes|Refs)" not in reusable


def test_render_workflows_single_provider_omits_the_other():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["gpt"])

    assert ".github/workflows/deepseek-pr-review.yml" not in files
    assert ".github/workflows/gpt-pr-review.yml" in files


def test_render_workflows_extras_can_be_individually_disabled():
    files = sra.render_workflows(
        "cicaid-devtools @ some-url",
        ["deepseek"],
        dependency_review=False,
        workflow_lint=False,
        codeql=False,
        pr_lint=False,
    )

    assert ".github/workflows/dependency-review.yml" not in files
    assert ".github/workflows/workflow-lint.yml" not in files
    assert ".github/workflows/codeql.yml" not in files
    assert ".github/workflows/pr-lint.yml" not in files

    # Issue templates are always installed, regardless of which extras are off.
    assert ".github/ISSUE_TEMPLATE/bug_report.md" in files
    assert ".github/ISSUE_TEMPLATE/config.yml" in files
    assert ".github/ISSUE_TEMPLATE/feature_request.md" in files


def test_render_workflows_changes_requested_label_add_and_remove_gates():
    """Issue #408: an approving run must remove the 'Changes Requested' label.

    The add step is gated on approved == 'false' and the remove step on
    approved == 'true', so a later approving run clears the label left by an
    earlier REQUEST CHANGES review instead of leaving it on merged PRs.
    """
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])

    reusable = files[".github/workflows/_ai-pr-review.yml"]
    add_step = (
        "- name: Add 'Changes Requested' label if review failed\n"
        "        if: steps.check_approval.outputs.approved == 'false'\n"
    )
    remove_step = (
        "- name: Remove 'Changes Requested' label if review approved\n"
        "        if: steps.check_approval.outputs.approved == 'true'\n"
    )
    assert add_step in reusable
    assert remove_step in reusable
    assert 'gh pr edit "$PR_NUMBER" --remove-label "Changes Requested"' in reusable


def test_pr_lint_cli_flag_can_be_enabled_or_disabled():
    parser = sra.build_arg_parser()

    assert parser.parse_args(["--pr-lint"]).pr_lint is True
    assert parser.parse_args(["--no-pr-lint"]).pr_lint is False
    assert parser.parse_args([]).pr_lint is None


def test_pr_lint_workflow_skips_draft_pull_requests():
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])

    workflow = files[".github/workflows/pr-lint.yml"]

    assert "ready_for_review" in workflow
    assert "github.event.pull_request.draft == false" in workflow


def test_render_workflows_codeql_uses_given_languages():
    files = sra.render_workflows(
        "cicaid-devtools @ some-url", ["deepseek"], codeql_languages=["java"]
    )

    codeql = files[".github/workflows/codeql.yml"]
    assert "language: ['java']" in codeql
    assert sra.CODEQL_LANGUAGES_PLACEHOLDER not in codeql


def test_render_workflows_codeql_supports_multiple_languages():
    files = sra.render_workflows(
        "cicaid-devtools @ some-url", ["deepseek"], codeql_languages=["python", "javascript"]
    )

    codeql = files[".github/workflows/codeql.yml"]
    assert "language: ['python', 'javascript']" in codeql


def test_render_codeql_languages_formats_as_yaml_flow_sequence():
    assert sra.render_codeql_languages(["python", "javascript"]) == "'python', 'javascript'"


def test_render_workflows_includes_issue_templates_matching_repo_files():
    """Drift guard: the embedded templates must stay identical to the repo's
    own .github/ISSUE_TEMPLATE/* (which are byte-identical to allotmint's)."""
    files = sra.render_workflows("cicaid-devtools @ some-url", ["deepseek"])
    repo_templates = Path(__file__).resolve().parents[1] / ".github" / "ISSUE_TEMPLATE"

    for rel_path in sra.ISSUE_TEMPLATE_FILES:
        assert rel_path in files
        expected = (repo_templates / Path(rel_path).name).read_text(encoding="utf-8")
        assert files[rel_path] == expected.replace("\r\n", "\n")


@pytest.mark.parametrize("providers", [["deepseek"], ["gpt"], ["deepseek", "gpt"]])
def test_render_workflows_produce_valid_yaml(providers):
    files = sra.render_workflows("cicaid-devtools @ some-url", providers)
    for path, content in files.items():
        # Markdown issue templates carry YAML frontmatter plus prose, so only
        # the workflow/yml files are expected to parse as a single YAML doc.
        if path.endswith(".yml"):
            yaml.safe_load(content)


# ─────────────────────────────── describe_included ──────────────────────────


def test_describe_included_lists_providers_and_every_detected_extra():
    paths = [
        ".github/workflows/_ai-pr-review.yml",
        ".github/workflows/deepseek-pr-review.yml",
        ".github/workflows/dependency-review.yml",
        ".github/workflows/workflow-lint.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/pr-lint.yml",
    ]
    assert sra.describe_included(["deepseek"], paths) == (
        "deepseek, dependency review, workflow lint, CodeQL, PR lint"
    )


def test_describe_included_omits_extras_not_present():
    paths = [".github/workflows/_ai-pr-review.yml", ".github/workflows/deepseek-pr-review.yml"]
    assert sra.describe_included(["deepseek"], paths) == "deepseek"


def test_describe_included_reflects_disabled_extras_via_render_workflows():
    """Guards against the title staying stale when an extra is toggled off."""
    files = sra.render_workflows(
        "cicaid-devtools @ some-url",
        ["deepseek", "gpt"],
        dependency_review=False,
        workflow_lint=False,
        codeql=False,
        pr_lint=False,
    )
    assert sra.describe_included(["deepseek", "gpt"], list(files)) == "deepseek, gpt"


# ──────────────────────────────── write_files ───────────────────────────────


def test_write_files_creates_parent_dirs_and_returns_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    written = sra.write_files({".github/workflows/foo.yml": "content"})

    assert written == [".github/workflows/foo.yml"]
    assert (tmp_path / ".github" / "workflows" / "foo.yml").read_text(encoding="utf-8") == "content"


# ─────────────────────────── build_issue_body / pr_body ────────────────────


def test_build_issue_body_lists_files_and_secrets():
    body = sra.build_issue_body(
        ["deepseek", "gpt"],
        [".github/workflows/_ai-pr-review.yml", ".github/workflows/deepseek-pr-review.yml"],
    )

    assert "DEEPSEEK_API_KEY" in body
    assert "OPENAI_API_KEY" in body
    assert ".github/workflows/_ai-pr-review.yml" in body
    assert "## Success looks like" in body


def test_build_pr_body_appends_closes_when_issue_number_given():
    body = sra.build_pr_body(["deepseek"], [".github/workflows/_ai-pr-review.yml"], "42")
    assert body.endswith("Closes #42")


def test_build_pr_body_omits_closes_when_no_issue_number():
    body = sra.build_pr_body(["deepseek"], [".github/workflows/_ai-pr-review.yml"], None)
    assert "Closes #" not in body


# ───────────────────────── create_branch_from_default ──────────────────────


def test_create_branch_from_default_reuses_existing_local_branch():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git fetch origin
            MagicMock(returncode=0),  # origin/<default> exists (no seeding needed)
            MagicMock(returncode=0),  # git rev-parse --verify <branch> succeeds (exists)
            MagicMock(),  # git checkout <branch>
            MagicMock(returncode=0),  # origin/<branch> also exists
        ]

        created = sra.create_branch_from_default("chore/issue-42-setup-review-actions", "main")

        assert created is False
        assert mock_run.call_args_list[1].args[0] == [
            "git",
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
        ]
        checkout_call = mock_run.call_args_list[3]
        assert checkout_call.args[0] == ["git", "checkout", "chore/issue-42-setup-review-actions"]
        assert mock_run.call_args_list[4].args[0] == [
            "git",
            "rev-parse",
            "--verify",
            "refs/remotes/origin/chore/issue-42-setup-review-actions",
        ]


def test_create_branch_from_default_resets_local_branch_deleted_from_remote():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git fetch --prune origin
            MagicMock(returncode=0),  # origin/<default> exists (no seeding needed)
            MagicMock(returncode=0),  # local branch exists
            MagicMock(),  # git checkout <branch>
            MagicMock(returncode=1),  # remote-tracking branch was pruned
            MagicMock(),  # git reset --hard origin/<default>
        ]

        created = sra.create_branch_from_default("chore/issue-42-setup-review-actions", "main")

        assert created is False
        assert mock_run.call_args_list[0].args[0] == ["git", "fetch", "--prune", "origin"]
        assert mock_run.call_args_list[5].args[0] == [
            "git",
            "reset",
            "--hard",
            "origin/main",
        ]


def test_create_branch_from_default_checks_out_new_branch():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git fetch origin
            MagicMock(returncode=0),  # origin/<default> exists (no seeding needed)
            MagicMock(returncode=1),  # git rev-parse --verify <branch> fails (doesn't exist)
            MagicMock(),  # git checkout -b <branch> origin/<default>
        ]

        created = sra.create_branch_from_default("chore/setup-review-actions", "main")

        assert created is True
        checkout_call = mock_run.call_args_list[3]
        assert checkout_call.args[0] == [
            "git", "checkout", "-b", "chore/setup-review-actions", "origin/main",
        ]


def test_create_branch_from_default_seeds_default_branch_on_empty_repo():
    """Fresh/empty repo: origin/<default> is missing, so seed an unborn local
    default branch with an empty initial commit, push it, then branch from it.
    """
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git fetch origin
            MagicMock(returncode=1),  # origin/main missing -> seed needed
            MagicMock(returncode=1),  # refs/heads/main missing -> checkout -b main
            MagicMock(),  # git checkout -b main
            MagicMock(returncode=1),  # HEAD still unborn -> needs the empty commit
            MagicMock(),  # git commit --allow-empty -m "Initial commit"
            MagicMock(),  # git push -u origin main
            MagicMock(returncode=1),  # local setup branch missing
            MagicMock(),  # git checkout -b <branch> origin/main
        ]

        created = sra.create_branch_from_default("chore/setup-review-actions", "main")

        assert created is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert calls[3] == ["git", "checkout", "-b", "main"]
        assert calls[5] == ["git", "commit", "--allow-empty", "-m", "Initial commit"]
        assert calls[6] == ["git", "push", "-u", "origin", "main"]
        assert calls[8] == [
            "git", "checkout", "-b", "chore/setup-review-actions", "origin/main",
        ]


def test_create_branch_from_default_seeds_by_pushing_existing_local_state():
    """Local default branch already exists with commits: seed by checking it out
    and pushing it, without inventing an extra empty commit.
    """
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(),  # git fetch origin
            MagicMock(returncode=1),  # origin/main missing -> seed needed
            MagicMock(returncode=0),  # refs/heads/main exists -> git checkout main
            MagicMock(),  # git checkout main
            MagicMock(returncode=0),  # HEAD resolves -> no empty commit
            MagicMock(),  # git push -u origin main
            MagicMock(returncode=1),  # local setup branch missing
            MagicMock(),  # git checkout -b <branch> origin/main
        ]

        created = sra.create_branch_from_default("chore/setup-review-actions", "main")

        assert created is True
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert calls[3] == ["git", "checkout", "main"]
        assert calls[5] == ["git", "push", "-u", "origin", "main"]
        assert calls[7] == [
            "git", "checkout", "-b", "chore/setup-review-actions", "origin/main",
        ]
        assert not any(c[0] == "git" and c[1] == "commit" for c in calls)


# ───────────────────────────── cleanup_local_branch ─────────────────────────


def test_cleanup_local_branch_checks_out_default_and_force_deletes_branch(caplog):
    caplog.set_level("INFO")
    with patch.object(sra.subprocess, "run") as mock_run:
        assert sra.cleanup_local_branch("chore/setup-review-actions", "main") is True

    assert mock_run.call_args_list[0].args[0] == ["git", "checkout", "main"]
    assert mock_run.call_args_list[1].args[0] == [
        "git", "branch", "-D", "chore/setup-review-actions",
    ]
    assert "Cleaned up local branch 'chore/setup-review-actions'" in caplog.text


def test_cleanup_local_branch_failure_is_reported_without_raising(caplog):
    with patch.object(
        sra.subprocess,
        "run",
        side_effect=subprocess.CalledProcessError(1, ["git", "checkout", "main"]),
    ):
        assert sra.cleanup_local_branch("chore/setup-review-actions", "main") is False

    assert "Could not clean up local branch 'chore/setup-review-actions'" in caplog.text


# ──────────────────────────── diff_against_default_branch ──────────────────


def test_diff_against_default_branch_flags_changed_and_missing_files():
    def fake_run(cmd, **kwargs):
        path = cmd[-1].split(":", 1)[1]
        if path == "unchanged.yml":
            return MagicMock(returncode=0, stdout="same content")
        if path == "changed.yml":
            return MagicMock(returncode=0, stdout="old content")
        return MagicMock(returncode=1, stdout="")  # missing.yml: not on the default branch

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        changed = sra.diff_against_default_branch(
            {
                "unchanged.yml": "same content",
                "changed.yml": "new content",
                "missing.yml": "new content",
            },
            "main",
        )

    assert set(changed) == {"changed.yml", "missing.yml"}


def test_diff_against_default_branch_empty_when_everything_matches():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="same content")

        changed = sra.diff_against_default_branch({"a.yml": "same content"}, "main")

    assert changed == {}


# ───────────────────────────────── derive_branch_name ───────────────────────


def test_derive_branch_name_uses_issue_number():
    assert sra.derive_branch_name("123") == "chore/issue-123-setup-review-actions"


def test_derive_branch_name_falls_back_without_issue():
    assert sra.derive_branch_name(None) == sra.DEFAULT_BRANCH_NAME


# ──────────────────────────────── main() validation ─────────────────────────


def test_main_rejects_unknown_provider(monkeypatch, caplog):
    import sys

    monkeypatch.setattr(sys, "argv", ["setup-review-actions", "--providers", "claude"])

    assert sra.main() == 1
    assert "Unknown provider" in caplog.text


def test_main_rejects_empty_providers(monkeypatch, caplog):
    import sys

    monkeypatch.setattr(sys, "argv", ["setup-review-actions", "--providers", " , "])

    assert sra.main() == 1
    assert "No providers selected" in caplog.text


def test_main_returns_early_when_nothing_changed(monkeypatch, tmp_path):
    """When the generated files already match the default branch, main() must
    bail out before filing a tracking issue or creating a branch -- otherwise
    a no-op rerun would spam a fresh issue every time.
    """
    import sys

    monkeypatch.setattr(sys, "argv", ["setup-review-actions"])
    monkeypatch.setattr(sra, "get_repo_root", lambda: str(tmp_path))
    monkeypatch.setattr(sra.os, "chdir", lambda p: None)
    monkeypatch.setattr(sra, "get_repo_info", lambda: ("owner", "repo"))
    monkeypatch.setattr(sra, "is_wiki_repo", lambda: False)
    monkeypatch.setattr(sra, "check_gh_available", lambda: None)
    monkeypatch.setattr(sra, "check_working_tree_clean", lambda: True)
    monkeypatch.setattr(sra, "get_default_branch", lambda owner, repo: "main")
    monkeypatch.setattr(sra, "get_cicaid_pro_install_spec", lambda: "cicaid-devtools @ some-url")
    monkeypatch.setattr(sra, "diff_against_default_branch", lambda files, default_branch: {})

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("should not be reached when nothing changed")

    monkeypatch.setattr(sra, "create_issue_via_api", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_gh", fail_if_called)
    monkeypatch.setattr(sra, "create_branch_from_default", fail_if_called)

    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = sra.main()

    assert result == 0


def _patch_repo_plumbing(monkeypatch, tmp_path):
    """Patch every git/GitHub plumbing dependency main() needs to reach the
    issue/branch/PR steps, without touching a real repo or network.
    """
    monkeypatch.setattr(sra, "get_repo_root", lambda: str(tmp_path))
    monkeypatch.setattr(sra.os, "chdir", lambda p: None)
    monkeypatch.setattr(sra, "get_repo_info", lambda: ("owner", "repo"))
    monkeypatch.setattr(sra, "is_wiki_repo", lambda: False)
    monkeypatch.setattr(sra, "check_gh_available", lambda: None)
    monkeypatch.setattr(sra, "check_working_tree_clean", lambda: True)
    monkeypatch.setattr(sra, "get_default_branch", lambda owner, repo: "main")
    monkeypatch.setattr(sra, "get_cicaid_pro_install_spec", lambda: "cicaid-devtools @ some-url")
    monkeypatch.setattr(
        sra, "diff_against_default_branch", lambda files, default_branch: dict(files)
    )
    monkeypatch.setattr(sra, "create_branch_from_default", lambda branch, default_branch: None)
    monkeypatch.setattr(sra, "write_files", lambda files: list(files))
    monkeypatch.setattr(sra, "push_to_remote", lambda branch: True)
    monkeypatch.setattr(sra, "ensure_dependency_graph_enabled", lambda owner, repo, token: None)


def test_main_no_issue_flag_skips_issue_and_pr_has_no_closes(monkeypatch, tmp_path):
    """--no-issue must never touch issue creation, and the resulting PR body
    must not carry a stale 'Closes #' reference. --no-dependency-review is
    also passed so this test isolates --no-issue -- dependency review's
    graph-enable step needs a token independently of issue creation.
    """
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--no-dependency-review", "--no-pr-lint"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("issue creation must be skipped when --no-issue is passed")

    monkeypatch.setattr(sra, "get_github_token", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_api", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_gh", fail_if_called)

    captured_pr = {}

    def fake_create_pr(owner, repo, branch, default_branch, title, body):
        captured_pr.update(branch=branch, title=title, body=body)
        return "https://github.com/owner/repo/pull/1"

    monkeypatch.setattr(sra, "create_pr", fake_create_pr)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return MagicMock(returncode=0, stdout=" M .github/workflows/_ai-pr-review.yml\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        result = sra.main()

    assert result == 0
    assert captured_pr["branch"] == sra.DEFAULT_BRANCH_NAME
    assert "Closes #" not in captured_pr["body"]


def test_main_returns_1_when_issue_creation_fails_both_ways(monkeypatch, tmp_path, caplog):
    """If both the API and gh-CLI issue creation fail, main() must hard-fail
    instead of silently continuing without the tracking issue (see #117's
    'An issue is created' acceptance criterion).
    """
    import sys

    monkeypatch.setattr(sys, "argv", ["setup-review-actions"])
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "get_github_token", lambda: "token")
    monkeypatch.setattr(sra, "create_issue_via_api", lambda *a, **k: None)
    monkeypatch.setattr(sra, "create_issue_via_gh", lambda *a, **k: None)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("should not reach branch creation once issue creation fails")

    monkeypatch.setattr(sra, "create_branch_from_default", fail_if_called)

    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = sra.main()

    assert result == 1
    assert "Failed to create the tracking issue" in caplog.text


@pytest.mark.parametrize(("branch_created", "cleanup_expected"), [(True, True), (False, False)])
def test_main_cleans_up_only_new_branch_when_push_fails(
    monkeypatch, tmp_path, branch_created, cleanup_expected
):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--no-dependency-review", "--no-pr-lint"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sra, "create_branch_from_default", lambda branch, default_branch: branch_created
    )
    monkeypatch.setattr(sra, "push_to_remote", lambda branch: False)
    cleanup = MagicMock()
    monkeypatch.setattr(sra, "cleanup_local_branch", cleanup)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return MagicMock(returncode=0, stdout=" M workflow.yml\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        assert sra.main() == 1

    assert cleanup.called is cleanup_expected
    if branch_created:
        cleanup.assert_called_once_with(sra.DEFAULT_BRANCH_NAME, "main")


# ─────────────────────────── --issue / auto-scan / link ─────────────────────


def test_build_arg_parser_accepts_issue_flag():
    args = sra.build_arg_parser().parse_args(
        ["--no-issue", "--issue", "22", "--no-dependency-review", "--no-codeql"]
    )
    assert args.issue == "22"
    assert args.no_issue is True


def test_issue_is_open_true_when_open():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"state": "open"}')
        assert sra.issue_is_open("owner", "repo", "22") is True
    assert mock_run.call_args.args[0][:6] == [
        "gh", "issue", "view", "22", "--repo", "owner/repo",
    ]


def test_issue_is_open_false_when_closed():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"state": "closed"}')
        assert sra.issue_is_open("owner", "repo", "22") is False


def test_issue_is_open_false_when_view_fails():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        assert sra.issue_is_open("owner", "repo", "9999") is False


def test_find_existing_tracking_issue_returns_most_recent():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                '[{"number": 21, "title": "Track GitHub Actions setup (deepseek)"}, '
                '{"number": 22, "title": "Track GitHub Actions setup (deepseek, gpt)"}]'
            ),
        )
        assert sra.find_existing_tracking_issue("owner", "repo") == "22"
    search_call = mock_run.call_args.args[0]
    assert "--search" in search_call
    assert '"Track GitHub Actions setup" in:title' in search_call


def test_find_existing_tracking_issue_returns_none_when_no_match():
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        assert sra.find_existing_tracking_issue("owner", "repo") is None


def test_find_existing_tracking_issue_returns_none_on_gh_failure(caplog):
    caplog.set_level("WARNING")
    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        assert sra.find_existing_tracking_issue("owner", "repo") is None
    assert "Could not search for an existing tracking issue" in caplog.text


def test_main_issue_flag_reuses_issue_closes_in_pr(monkeypatch, tmp_path):
    """--no-issue --issue 22: no new issue, branch named after #22, PR body ends
    with 'Closes #22', and commit references #22.
    """
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--issue", "22", "--no-dependency-review"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "issue_is_open", lambda owner, repo, number: True)
    monkeypatch.setattr(sra, "get_github_token", lambda: "token")

    captured_pr = {}

    def fake_create_pr(owner, repo, branch, default_branch, title, body):
        captured_pr.update(branch=branch, title=title, body=body)
        return "https://github.com/owner/repo/pull/23"

    monkeypatch.setattr(sra, "create_pr", fake_create_pr)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("issue creation must be skipped when --issue is passed")

    monkeypatch.setattr(sra, "create_issue_via_api", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_gh", fail_if_called)

    commit_messages = []

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return MagicMock(returncode=0, stdout=" M .github/workflows/_ai-pr-review.yml\n")
        if cmd[0] == "git" and cmd[1] == "commit":
            commit_messages.append(cmd[cmd.index("-m") + 1])
        return MagicMock(returncode=0, stdout="")

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        result = sra.main()

    assert result == 0
    assert captured_pr["branch"] == "chore/issue-22-setup-review-actions"
    assert captured_pr["body"].endswith("Closes #22")
    assert commit_messages and "Refs #22" in commit_messages[0]


def test_main_no_issue_auto_reuses_existing_tracking_issue(monkeypatch, tmp_path):
    """--no-issue without --issue finds the crashed run's tracker and closes it."""
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--no-dependency-review"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "find_existing_tracking_issue", lambda owner, repo: "22")
    monkeypatch.setattr(sra, "get_github_token", lambda: "token")

    captured_pr = {}

    def fake_create_pr(owner, repo, branch, default_branch, title, body):
        captured_pr.update(branch=branch, title=title, body=body)
        return "https://github.com/owner/repo/pull/23"

    monkeypatch.setattr(sra, "create_pr", fake_create_pr)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("issue creation must be skipped when --no-issue is passed")

    monkeypatch.setattr(sra, "create_issue_via_api", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_gh", fail_if_called)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return MagicMock(returncode=0, stdout=" M workflow.yml\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        result = sra.main()

    assert result == 0
    assert captured_pr["branch"] == "chore/issue-22-setup-review-actions"
    assert captured_pr["body"].endswith("Closes #22")


def test_main_default_path_reuses_existing_tracking_issue(monkeypatch, tmp_path):
    """Plain re-run (no --no-issue/--issue flags) reuses the open tracker from a
    crashed run instead of filing a duplicate, and the PR still closes it.
    """
    import sys

    monkeypatch.setattr(sys, "argv", ["setup-review-actions", "--no-dependency-review"])
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "find_existing_tracking_issue", lambda owner, repo: "22")
    monkeypatch.setattr(sra, "get_github_token", lambda: "token")

    captured_pr = {}

    def fake_create_pr(owner, repo, branch, default_branch, title, body):
        captured_pr.update(branch=branch, title=title, body=body)
        return "https://github.com/owner/repo/pull/23"

    monkeypatch.setattr(sra, "create_pr", fake_create_pr)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("issue creation must be skipped when a tracker is reused")

    monkeypatch.setattr(sra, "create_issue_via_api", fail_if_called)
    monkeypatch.setattr(sra, "create_issue_via_gh", fail_if_called)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return MagicMock(returncode=0, stdout=" M workflow.yml\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(sra.subprocess, "run", side_effect=fake_run):
        result = sra.main()

    assert result == 0
    assert captured_pr["branch"] == "chore/issue-22-setup-review-actions"
    assert captured_pr["body"].endswith("Closes #22")


def test_main_no_issue_fails_fast_when_no_tracker_and_pr_lint_enabled(
    monkeypatch, tmp_path, caplog
):
    """--no-issue with pr-lint on and no tracker to reference must fail before
    the branch/PR steps instead of opening a PR that fails its own lint.
    """
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--no-dependency-review"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "find_existing_tracking_issue", lambda owner, repo: None)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("must not create branch/PR when the reference check fails")

    monkeypatch.setattr(sra, "create_branch_from_default", fail_if_called)
    monkeypatch.setattr(sra, "create_pr", fail_if_called)

    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = sra.main()

    assert result == 1
    assert "Pass --issue <number>" in caplog.text


def test_main_issue_flag_fails_when_issue_not_open(monkeypatch, tmp_path, caplog):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup-review-actions", "--no-issue", "--issue", "22", "--no-dependency-review"],
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)
    monkeypatch.setattr(sra, "issue_is_open", lambda owner, repo, number: False)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("must not open a PR when the referenced issue is not open")

    monkeypatch.setattr(sra, "create_branch_from_default", fail_if_called)
    monkeypatch.setattr(sra, "create_pr", fail_if_called)

    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = sra.main()

    assert result == 1
    assert "does not exist or is not open" in caplog.text


def test_main_rejects_non_numeric_issue(monkeypatch, tmp_path, caplog):
    import sys

    monkeypatch.setattr(
        sys, "argv", ["setup-review-actions", "--issue", "abc", "--no-dependency-review"]
    )
    _patch_repo_plumbing(monkeypatch, tmp_path)

    with patch.object(sra.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = sra.main()

    assert result == 1
    assert "expects a numeric issue number" in caplog.text
