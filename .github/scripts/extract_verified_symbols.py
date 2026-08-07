"""Extract class/method names from changed files and verify they exist in the codebase."""

from __future__ import annotations
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
import argparse
import re
import subprocess
import sys


def extract_symbols_from_diff(diff_text: str) -> set[str]:
    """Extract potential class and function/method names from a diff (Python + Java)."""
    symbols = set()

    # Python patterns
    py_class_pattern = r'^\+.*?\bclass\s+([A-Z]\w*)'
    py_func_pattern = r'^\+.*?\bdef\s+([a-z_]\w*)\s*\('

    # Java patterns
    java_type_pattern = r'^\+.*?\b(?:class|interface|record|enum)\s+([A-Z]\w+)'
    java_method_pattern = r'^\+.*?\b(?:public|private|protected|static|final|synchronized)\b[^;{]*?\s([a-z]\w*)\s*\('

    for line in diff_text.splitlines():
        # Look at added lines only
        if line.startswith('+') and not line.startswith('+++'):
            for pat in (py_class_pattern, py_func_pattern, java_type_pattern, java_method_pattern):
                m = re.search(pat, line)
                if m:
                    symbols.add(m.group(1))

    return symbols


def verify_symbol_exists(symbol: str) -> bool:
    """Check if a symbol exists in the codebase using grep (Python and Java files)."""
    includes = ['*.py', '*.java', '*.yml', '*.yaml', '*.md', '*.sh', '*.toml']
    try:
        grep_args = ['grep', '-r', f'\\b{re.escape(symbol)}\\b']
        for inc in includes:
            grep_args.extend(['--include', inc])
        result = subprocess.run(
            grep_args,
            capture_output=True,
            timeout=5,
            cwd='.',
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main() -> int:
    """Extract symbols and generate a verified facts entry."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--diff', required=True, help='The PR diff text')
    args = parser.parse_args()

    symbols = extract_symbols_from_diff(args.diff)
    if not symbols:
        print("")
        return 0

    # Verify each symbol exists in the codebase
    verified = []
    for symbol in sorted(symbols):
        if verify_symbol_exists(symbol):
            verified.append(f"`{symbol}`")
            # Limit output to top 5 verified symbols to avoid excessive facts
            if len(verified) >= 5:
                break

    if verified:
        facts = "**Classes/methods confirmed present in codebase:** " + ", ".join(verified) + "."
        print(facts)
    else:
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
