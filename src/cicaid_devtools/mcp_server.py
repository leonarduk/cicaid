"""Expose cicaid commands (and any installed extension's, e.g. cicaid-pro) as
an MCP server, so MCP-capable clients can call them as typed tools with
structured results instead of shelling out and parsing log lines.

Requires the optional `mcp` extra: `pip install cicaid-devtools[mcp]`.

Each discovered command (see `cli.discover_commands()` -- this repo's own
commands plus any registered under the `cicaid.commands` entry-point group,
which is how cicaid-pro's LLM-backed commands show up when that package is
installed alongside this one) becomes one MCP tool, named after the command
with dashes replaced by underscores (MCP tool names must be valid
identifiers). Each tool takes the same flags/arguments the command's own
`--help` documents, as a single `args` list, e.g. calling the `work_on_pr`
tool with `args=["123"]` is equivalent to running `cicaid work-on-pr 123`.

Commands are invoked as a subprocess of the `cicaid` CLI itself
(`python -m cicaid_devtools.cli <command> <args...>`) rather than by calling
each command module's `main()` in-process. That's deliberate, not a
shortcut: most command modules configure `logging` at import time with a
`StreamHandler` bound to whatever `sys.stderr` was at that moment, so
capturing a second (or third, ...) in-process call's output by swapping
`sys.stderr` around it would miss anything that command logs -- the handler
already grabbed a reference to the *previous* stream. A real subprocess
sidesteps that entirely and gives back its actual stdout/stderr/exit code,
at the (here, negligible) cost of a fresh interpreter start per call --
these commands already shell out to `git`/`gh` themselves, so one more
process per call is not a meaningful overhead.
"""

from __future__ import annotations

import os
import subprocess
import sys

from cicaid_devtools.cli import discover_commands

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised via the message, not the import
    raise SystemExit(
        "fastmcp is required for the MCP server. Install it with "
        "`pip install cicaid-devtools[mcp]`."
    ) from exc

SERVER_NAME = "cicaid"
COMMAND_TIMEOUT_SECONDS = 600


def _as_text(value: str | bytes | None) -> str:
    """Normalize a subprocess stdout/stderr value to str.

    ``subprocess.TimeoutExpired.stdout``/``.stderr`` are the raw undecoded
    bytes buffers even when the call used ``text=True``/``encoding=`` --
    CPython's timeout path raises before those arguments get applied.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_command(command: str, args: list[str] | None = None) -> dict:
    """Run `cicaid <command> <args...>` as a subprocess, returning structured output.

    Never raises for a command that runs and fails -- the failure is
    reported in the returned dict (`success: False`, plus `stderr`) so an
    MCP client can act on it programmatically instead of catching an
    exception. Stdin is closed and CICAID_NON_INTERACTIVE is set so a
    command that would otherwise prompt (see lib/interactive.py) fails fast
    with a clear error instead of blocking on input the MCP transport can't
    supply (stdio transport's stdin is the JSON-RPC pipe; an HTTP-transport
    server started from a terminal has a real tty for stdin otherwise).
    """
    cmd = [sys.executable, "-m", "cicaid_devtools.cli", command, *(args or [])]
    env = {**os.environ, "CICAID_NON_INTERACTIVE": "1"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "success": False,
            "stdout": _as_text(exc.stdout),
            "stderr": (
                _as_text(exc.stderr) + f"\n[cicaid-mcp] timed out after {COMMAND_TIMEOUT_SECONDS}s"
            ),
        }
    return {
        "exit_code": result.returncode,
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _make_tool(command: str, tool_name: str):
    """Build a standalone tool function bound to `command` via closure.

    A factory function (rather than a default-arg trick on a function
    defined inline in the registration loop) keeps the bound command name
    out of the function's signature entirely -- FastMCP introspects the
    signature to build each tool's public input schema, so a default-arg
    binding would advertise (and let a caller override) an undocumented
    `_command` parameter on every tool.
    """

    def tool(args: list[str] | None = None) -> dict:
        return run_command(command, args)

    tool.__name__ = tool_name
    return tool


def build_server() -> FastMCP:
    """Build a FastMCP server with one tool per discovered cicaid command."""
    mcp = FastMCP(SERVER_NAME)
    for name, (_module_name, description) in discover_commands().items():
        tool_name = name.replace("-", "_")
        mcp.tool(
            _make_tool(name, tool_name),
            name=tool_name,
            description=description or f"Run cicaid's `{name}` command.",
        )
    return mcp


def main() -> None:
    """Entry point for the `cicaid-mcp` console script."""
    build_server().run()


if __name__ == "__main__":
    main()
