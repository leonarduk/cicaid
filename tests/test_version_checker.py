"""Tests for the interactive release updater."""

from __future__ import annotations

import ctypes
import glob
import subprocess
import sys
import sysconfig
from types import SimpleNamespace

import pytest
import requests

from cicaid_devtools import version_checker


def test_latest_release_uses_matching_asset(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "tag_name": "v1.2.3",
                "assets": [
                    {
                        "name": "cicaid_devtools-1.2.3-py3-none-any.whl",
                        "browser_download_url": "https://example.test/cicaid.whl",
                    }
                ],
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    assert version_checker.latest_release() == version_checker.Release(
        "1.2.3", "https://example.test/cicaid.whl"
    )


def test_latest_release_accepts_normalized_wheel_version(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "tag_name": "v0.7.0",
                "assets": [
                    {
                        "name": "cicaid_devtools-0.7-py3-none-any.whl",
                        "browser_download_url": "https://example.test/cicaid-0.7.whl",
                    }
                ],
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())

    assert version_checker.latest_release() == version_checker.Release(
        "0.7.0", "https://example.test/cicaid-0.7.whl"
    )


def test_latest_release_ignores_other_packages_and_versions(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "tag_name": "v1.2.3",
                "assets": [
                    {
                        "name": "another_package-1.2.3-py3-none-any.whl",
                        "browser_download_url": "https://example.test/another.whl",
                    },
                    {
                        "name": "cicaid_devtools-1.2.2-py3-none-any.whl",
                        "browser_download_url": "https://example.test/old.whl",
                    },
                ],
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())

    with pytest.raises(ValueError, match="no compatible cicaid_devtools-1.2.3"):
        version_checker.latest_release()


def test_latest_release_rejects_release_without_wheel(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v1.2.3", "assets": []}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())

    missing_wheel = (
        "GitHub release v1.2.3 has no compatible cicaid_devtools-1.2.3-py3-none-any.whl asset"
    )
    with pytest.raises(ValueError, match=missing_wheel):
        version_checker.latest_release()


def test_available_update_detects_newer_version(monkeypatch):
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")
    release = version_checker.Release("1.1.0", "https://example.test/new.whl")
    monkeypatch.setattr(version_checker, "latest_release", lambda: release)
    assert version_checker.available_update() == release


def test_available_update_ignores_current_or_older_version(monkeypatch):
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.1.0")
    monkeypatch.setattr(
        version_checker,
        "latest_release",
        lambda: version_checker.Release("1.1.0", "https://example.test/current.whl"),
    )
    assert version_checker.available_update() is None


def test_available_update_ignores_network_failure(monkeypatch):
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")

    def fail():
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(version_checker, "latest_release", fail)
    assert version_checker.available_update() is None


def test_available_update_warns_and_ignores_invalid_release(monkeypatch, caplog):
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")

    def fail():
        raise ValueError("release has no matching wheel")

    monkeypatch.setattr(version_checker, "latest_release", fail)

    assert version_checker.available_update() is None
    assert "Unable to check for a cicaid update: release has no matching wheel" in caplog.messages


def test_check_does_nothing_when_not_interactive(monkeypatch):
    monkeypatch.setattr(version_checker.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        version_checker, "available_update", lambda: (_ for _ in ()).throw(AssertionError())
    )
    version_checker.check_and_prompt()


def test_check_prompts_and_ignores_update(monkeypatch):
    release = version_checker.Release("2.0.0", "https://example.test/new.whl")
    monkeypatch.setattr(version_checker.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(version_checker.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(version_checker, "available_update", lambda: release)
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    monkeypatch.setattr(
        version_checker, "install_update", lambda release: (_ for _ in ()).throw(AssertionError())
    )
    version_checker.check_and_prompt()


def test_check_installs_and_restarts(monkeypatch):
    release = version_checker.Release("2.0.0", "https://example.test/new.whl")
    monkeypatch.setattr(version_checker.os, "name", "posix")
    monkeypatch.setattr(version_checker.sys, "platform", "linux")
    monkeypatch.setattr(version_checker.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(version_checker.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(version_checker, "available_update", lambda: release)
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    monkeypatch.setattr(version_checker, "install_update", lambda candidate: candidate == release)
    restarted = []
    monkeypatch.setattr(
        version_checker.os, "execv", lambda executable, args: restarted.append(args)
    )

    version_checker.check_and_prompt()

    assert restarted == [[version_checker.sys.executable, *version_checker.sys.argv]]


def test_windows_update_is_deferred_until_current_process_exits(monkeypatch):
    release = version_checker.Release("2.0.0", "https://example.test/new.whl")
    started = []

    monkeypatch.setattr(version_checker.os, "name", "nt")
    monkeypatch.setattr(version_checker.os, "getpid", lambda: 1234)
    monkeypatch.setattr(
        version_checker.subprocess, "Popen", lambda *a, **kw: started.append((a, kw))
    )

    assert version_checker.install_update(release)
    command = started[0][0][0]
    assert command[:3] == [
        version_checker.sys.executable,
        "-c",
        version_checker._WINDOWS_UPDATE_SCRIPT,
    ]
    assert command[3:5] == ["1234", release.wheel_url]
    assert started[0][1]["creationflags"] == 0x00000008 | 0x00000200
    assert "WaitForSingleObject" in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "WaitForSingleObject(handle, 30000)" in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "0xFFFFFFFF" not in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "wait_result == 0" in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "wait_result == 0x102" in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "Timed out after 30 seconds" in version_checker._WINDOWS_UPDATE_SCRIPT
    assert '"~icaid_devtools*"' in version_checker._WINDOWS_UPDATE_SCRIPT


def test_windows_update_helper_is_valid_python():
    compile(version_checker._WINDOWS_UPDATE_SCRIPT, "<windows-update-helper>", "exec")

    assert '"~icaid_devtools*"' in version_checker._WINDOWS_UPDATE_SCRIPT
    assert "from cicaid_devtools" not in version_checker._WINDOWS_UPDATE_SCRIPT


def _run_windows_update_helper(monkeypatch, tmp_path, *, pip_result):
    """Execute the real embedded updater script against a stubbed pip run."""
    log_path = tmp_path / "update.log"
    commands = []

    kernel32 = SimpleNamespace(OpenProcess=lambda *args: 0)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)
    monkeypatch.setattr(sysconfig, "get_path", lambda name: None)
    monkeypatch.setattr(
        glob,
        "glob",
        lambda pattern: (_ for _ in ()).throw(AssertionError(f"unexpected glob: {pattern}")),
    )

    def run(command, **kwargs):
        commands.append(command)
        return pip_result

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["windows-update-helper", "1234", "https://example.test/new.whl", str(log_path)],
    )

    with pytest.raises(SystemExit, match=str(pip_result.returncode)):
        exec(compile(version_checker._WINDOWS_UPDATE_SCRIPT, "<windows-update-helper>", "exec"))

    assert commands == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "cicaid-devtools @ https://example.test/new.whl",
        ]
    ]
    return log_path.read_text(encoding="utf-8")


def test_windows_update_reports_executable_lock_with_manual_command(monkeypatch, tmp_path):
    pip_result = subprocess.CompletedProcess(
        args=["pip"],
        returncode=1,
        stdout="ERROR: [WinError 32] The process cannot access cicaid.exe because it is "
        "being used by another process\n",
    )

    output = _run_windows_update_helper(monkeypatch, tmp_path, pip_result=pip_result)

    assert pip_result.stdout in output
    assert "can't replace its own running .exe on Windows" in output
    assert "After cicaid exits" in output
    assert "cicaid-devtools @ https://example.test/new.whl" in output


def test_windows_update_failure_without_lock_only_preserves_pip_output(monkeypatch, tmp_path):
    pip_result = subprocess.CompletedProcess(
        args=["pip"], returncode=1, stdout="ERROR: Network connection timed out\n"
    )

    output = _run_windows_update_helper(monkeypatch, tmp_path, pip_result=pip_result)

    assert output.endswith(pip_result.stdout)
    assert "can't replace its own running .exe on Windows" not in output


def test_windows_update_helper_ignores_missing_install_roots(monkeypatch, tmp_path):
    pip_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Successfully installed\n"
    )

    output = _run_windows_update_helper(monkeypatch, tmp_path, pip_result=pip_result)

    assert output.endswith("Successfully installed\n")


def test_windows_prompt_exits_after_scheduling_update(monkeypatch, capsys):
    release = version_checker.Release("2.0.0", "https://example.test/new.whl")
    monkeypatch.setattr(version_checker.os, "name", "nt")
    monkeypatch.setattr(version_checker.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(version_checker.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(version_checker, "available_update", lambda: release)
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    monkeypatch.setattr(version_checker, "install_update", lambda candidate: True)

    with pytest.raises(SystemExit, match="0"):
        version_checker.check_and_prompt()

    assert "will update after this process exits" in capsys.readouterr().out


def test_windows_prompt_gives_manual_command_when_helper_fails(monkeypatch, capsys):
    release = version_checker.Release("2.0.0", "https://example.test/new.whl")
    monkeypatch.setattr(version_checker.os, "name", "nt")
    monkeypatch.setattr(version_checker.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(version_checker.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(version_checker, "available_update", lambda: release)
    monkeypatch.setattr(version_checker, "installed_version", lambda: "1.0.0")
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    monkeypatch.setattr(version_checker, "install_update", lambda candidate: False)

    version_checker.check_and_prompt()

    assert "Close cicaid and run" in capsys.readouterr().err
