"""Check GitHub releases for a newer cicaid-devtools version and install it."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

import requests
from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import InvalidVersion, Version

from cicaid_devtools.lib.interactive import NON_INTERACTIVE_ENV

PACKAGE_NAME = "cicaid-devtools"
LATEST_RELEASE_URL = "https://api.github.com/repos/leonarduk/cicaid/releases/latest"
SKIP_UPDATE_ENV = "CICAID_SKIP_UPDATE_CHECK"

logger = logging.getLogger(__name__)
_WINDOWS_UPDATE_SCRIPT = r"""
import ctypes
import glob
import os
import shutil
import subprocess
import sys
import sysconfig


def write_update_result(result, log, wheel_url):
    # Stay self-contained: pip may be replacing the installed package files.
    output = result.stdout or ""
    print(output, end="", file=log)
    lock_error = "WinError 32" in output or "being used by another process" in output
    if result.returncode != 0 and lock_error:
        print(
            "\ncicaid can't replace its own running .exe on Windows. After cicaid "
            "exits, open a new terminal and run: "
            f'`"{sys.executable}" -m pip install --upgrade '
            f'"cicaid-devtools @ {wheel_url}"`',
            file=log,
        )

parent_pid, wheel_url, log_path = int(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(log_path, "w", encoding="utf-8") as log:
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, parent_pid)
    if handle:
        try:
            wait_result = ctypes.windll.kernel32.WaitForSingleObject(handle, 30000)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

        if wait_result == 0:  # WAIT_OBJECT_0
            print("Parent process exited; starting cicaid update.", file=log)
        elif wait_result == 0x102:  # WAIT_TIMEOUT
            print(
                "WARNING: Timed out after 30 seconds waiting for the parent process; "
                "cicaid update aborted.",
                file=log,
            )
            raise SystemExit(1)
        else:
            print(
                f"Waiting for the parent process failed with status {wait_result:#x}; "
                "cicaid update aborted.",
                file=log,
            )
            raise SystemExit(1)
    else:
        print("Parent process already exited; starting cicaid update.", file=log)

    # pip prefixes an incompletely removed distribution with ``~``.  Remove only
    # cicaid's abandoned entries before retrying so the invalid-distribution
    # warning does not survive a previously interrupted update.
    roots = {
        root
        for root in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib"))
        if root is not None
    }
    for root in roots:
        for pattern in ("~icaid_devtools*", "~icaid-devtools*"):
            for path in glob.glob(os.path.join(root, pattern)):
                try:
                    shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
                except OSError as exc:
                    print(f"Could not remove stale distribution {path}: {exc}", file=log)

    command = [
        sys.executable, "-m", "pip", "install", "--upgrade",
        f"cicaid-devtools @ {wheel_url}",
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    write_update_result(result, log, wheel_url)
    raise SystemExit(result.returncode)
"""


@dataclass(frozen=True)
class Release:
    """The version and wheel URL of a published release."""

    version: str
    wheel_url: str


def installed_version() -> str | None:
    """Return the installed distribution version, or ``None`` in a source checkout."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return None


def latest_release(*, timeout: float = 2.0) -> Release:
    """Fetch and validate the latest release metadata from GitHub."""
    response = requests.get(
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        raise ValueError("GitHub's latest release has no tag_name")

    release_version = tag.removeprefix("v")
    Version(release_version)  # Reject malformed or unexpected release tags.
    expected_wheel_name = f"cicaid_devtools-{release_version}-py3-none-any.whl"
    assets = payload.get("assets", [])
    wheel_url = None
    for asset in assets:
        asset_name = asset.get("name")
        asset_url = asset.get("browser_download_url")
        if not isinstance(asset_name, str) or not asset_url:
            continue
        try:
            distribution, asset_version, _, _ = parse_wheel_filename(asset_name)
        except InvalidWheelFilename:
            continue
        # setuptools-scm normalizes tags such as 0.7.0 to the PEP 440 version
        # 0.7 when it builds the wheel. Compare parsed versions rather than
        # requiring the tag's spelling to appear verbatim in the filename.
        if distribution == "cicaid-devtools" and asset_version == Version(release_version):
            wheel_url = asset_url
            break
    if wheel_url is None:
        raise ValueError(f"GitHub release {tag} has no compatible {expected_wheel_name} asset")
    return Release(release_version, wheel_url)


def available_update() -> Release | None:
    """Return a newer release, failing silently when an online check is unavailable."""
    current = installed_version()
    if current is None:
        return None
    try:
        release = latest_release()
    except ValueError as exc:
        logger.warning("Unable to check for a cicaid update: %s", exc)
        return None
    except (KeyError, TypeError, requests.RequestException):
        return None

    try:
        return release if Version(release.version) > Version(current) else None
    except (InvalidVersion, TypeError, ValueError):
        return None


def install_update(release: Release) -> bool:
    """Install *release* with the current interpreter's pip."""
    if os.name == "nt":
        return _defer_windows_update(release)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"{PACKAGE_NAME} @ {release.wheel_url}",
        ],
        check=False,
    )
    return result.returncode == 0


def _defer_windows_update(release: Release) -> bool:
    """Start a detached updater which waits until Windows unlocks cicaid.exe."""
    log_path = os.path.join(tempfile.gettempdir(), "cicaid-update.log")
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _WINDOWS_UPDATE_SCRIPT,
                str(os.getpid()),
                release.wheel_url,
                log_path,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            # These numeric values are stable Win32 flags and remain testable on POSIX.
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        )
    except OSError:
        return False
    return True


def check_and_prompt() -> None:
    """Offer an update in interactive sessions and restart after installing it."""
    if (
        os.environ.get(SKIP_UPDATE_ENV)
        or os.environ.get(NON_INTERACTIVE_ENV)
        or not (sys.stdin.isatty() and sys.stdout.isatty())
    ):
        return

    release = available_update()
    if release is None:
        return

    current = installed_version()
    answer = input(
        f"cicaid {release.version} is available (installed: {current}). Update now? [y/N] "
    )
    if answer.strip().lower() not in {"y", "yes"}:
        return
    if not install_update(release):
        if os.name == "nt":
            print(
                "Unable to start the cicaid updater. Close cicaid and run "
                f'`"{sys.executable}" -m pip install --upgrade {PACKAGE_NAME}`.',
                file=sys.stderr,
            )
        else:
            print("cicaid update failed; continuing with the installed version.", file=sys.stderr)
        return

    if os.name == "nt":
        log_path = os.path.join(tempfile.gettempdir(), "cicaid-update.log")
        print(
            "cicaid will update after this process exits. "
            f"Update details will be written to {log_path}."
        )
        raise SystemExit(0)

    print("Update installed. Restarting cicaid...")
    os.execv(sys.executable, [sys.executable, *sys.argv])
