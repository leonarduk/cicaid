import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

fastmcp = pytest.importorskip("fastmcp")

from cicaid_devtools import mcp_server  # noqa: E402


def test_run_command_reports_success():
    completed = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with patch.object(mcp_server.subprocess, "run", return_value=completed) as run:
        result = mcp_server.run_command("sync-issues", ["--dry-run"])

    run.assert_called_once()
    cmd = run.call_args.args[0]
    assert cmd[-2:] == ["sync-issues", "--dry-run"]
    assert result == {"exit_code": 0, "success": True, "stdout": "ok\n", "stderr": ""}


def test_run_command_closes_stdin_and_sets_non_interactive():
    completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch.object(mcp_server.subprocess, "run", return_value=completed) as run:
        mcp_server.run_command("work-on-pr", [])

    kwargs = run.call_args.kwargs
    assert kwargs["stdin"] == mcp_server.subprocess.DEVNULL
    assert kwargs["env"]["CICAID_NON_INTERACTIVE"] == "1"


def test_run_command_reports_failure_without_raising():
    completed = MagicMock(returncode=1, stdout="", stderr="boom\n")
    with patch.object(mcp_server.subprocess, "run", return_value=completed):
        result = mcp_server.run_command("run-ci-checks", ["--check", "nope"])

    assert result["success"] is False
    assert result["exit_code"] == 1
    assert result["stderr"] == "boom\n"


def test_run_command_handles_timeout():
    """subprocess.TimeoutExpired.stdout/.stderr are the raw undecoded bytes
    buffers even when the call used text=True/encoding= -- CPython's timeout
    path raises before those arguments get applied. Using bytes here (not
    str) is what makes this test faithful to the real exception shape."""
    timeout_exc = subprocess.TimeoutExpired(
        cmd=["cicaid"], timeout=1, output=b"partial", stderr=b"stuck"
    )
    with patch.object(mcp_server.subprocess, "run", side_effect=timeout_exc):
        result = mcp_server.run_command("run-ci-checks", ["--all"])

    assert result["success"] is False
    assert result["exit_code"] is None
    assert result["stdout"] == "partial"
    assert "stuck" in result["stderr"]
    assert "timed out" in result["stderr"]


def _get_tools(server):
    import asyncio

    return asyncio.run(server.get_tools())


def test_build_server_registers_one_tool_per_discovered_command():
    fake_commands = {
        "sync-issues": ("cicaid_devtools.sync_issues", "Sync GitHub issues"),
        "work-on-pr": ("cicaid_devtools.work_on_pr", "Check out the branch for an open PR"),
    }
    with patch.object(mcp_server, "discover_commands", return_value=fake_commands):
        server = mcp_server.build_server()

    tools = _get_tools(server)
    assert set(tools) == {"sync_issues", "work_on_pr"}
    assert tools["sync_issues"].description == "Sync GitHub issues"


def test_build_server_tools_each_dispatch_their_own_command():
    """Regression guard for a closure-in-a-loop bug: each tool must call its
    OWN command, not whichever command happened to be bound last."""
    fake_commands = {
        "work-on-pr": ("cicaid_devtools.work_on_pr", "desc a"),
        "sync-issues": ("cicaid_devtools.sync_issues", "desc b"),
    }
    with patch.object(mcp_server, "discover_commands", return_value=fake_commands):
        server = mcp_server.build_server()

    tools = _get_tools(server)
    with patch.object(mcp_server, "run_command", return_value={"success": True}) as run_command:
        tools["work_on_pr"].fn(["123"])
        tools["sync_issues"].fn(["--dry-run"])

    assert run_command.call_args_list == [
        call("work-on-pr", ["123"]),
        call("sync-issues", ["--dry-run"]),
    ]


def test_build_server_tool_schema_does_not_leak_bound_command():
    """The command-name binding must not be a caller-visible/overridable
    parameter on the tool's public MCP schema."""
    fake_commands = {"work-on-pr": ("cicaid_devtools.work_on_pr", "desc")}
    with patch.object(mcp_server, "discover_commands", return_value=fake_commands):
        server = mcp_server.build_server()

    tools = _get_tools(server)
    assert "_command" not in tools["work_on_pr"].parameters.get("properties", {})


def test_main_requires_fastmcp_when_missing(monkeypatch):
    """Regression guard: the ImportError -> SystemExit translation at import
    time must name the [mcp] extra, since this dependency is optional."""
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "fastmcp", None)
    with pytest.raises(SystemExit, match=r"\[mcp\]"):
        importlib.reload(mcp_server)

    # Restore the real module for any tests that run after this one.
    monkeypatch.delitem(sys.modules, "fastmcp", raising=False)
    importlib.reload(mcp_server)
