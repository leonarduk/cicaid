from pathlib import Path

import pytest

from cicaid_devtools.run_ci_checks import (
    Check,
    DEFAULT_CHECKS,
    load_checks,
    select_checks,
)


def test_load_checks_falls_back_to_default_when_no_config(tmp_path):
    assert load_checks(tmp_path) == DEFAULT_CHECKS


def test_load_checks_reads_toml_config(tmp_path):
    config = tmp_path / ".cicaid-checks.toml"
    config.write_text(
        """
[[checks]]
name = "build"
description = "Maven build"
workflow = ".github/workflows/build.yml"
commands = ["./mvnw verify"]
""",
        encoding="utf-8",
    )
    checks = load_checks(tmp_path)
    assert checks == (
        Check("build", "Maven build", ".github/workflows/build.yml", ("./mvnw verify",)),
    )


def test_load_checks_explicit_missing_path_raises(tmp_path):
    with pytest.raises(SystemExit):
        load_checks(tmp_path, tmp_path / "nope.toml")


def test_load_checks_empty_checks_list_raises(tmp_path):
    config = tmp_path / ".cicaid-checks.toml"
    config.write_text("checks = []\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_checks(tmp_path, config)


def test_load_checks_missing_required_key_raises(tmp_path):
    config = tmp_path / ".cicaid-checks.toml"
    config.write_text('[[checks]]\nname = "build"\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        load_checks(tmp_path, config)


def test_select_checks_all():
    args = _args(all=True, check=None)
    assert select_checks(args, DEFAULT_CHECKS) == list(DEFAULT_CHECKS)


def test_select_checks_by_name():
    args = _args(all=False, check=["frontend"])
    result = select_checks(args, DEFAULT_CHECKS)
    assert [c.name for c in result] == ["frontend"]


def test_select_checks_unknown_name_raises():
    args = _args(all=False, check=["not-a-real-check"])
    with pytest.raises(SystemExit):
        select_checks(args, DEFAULT_CHECKS)


class _Args:
    def __init__(self, all, check):
        self.all = all
        self.check = check


def _args(all, check):
    return _Args(all, check)
