from pathlib import Path

from cicaid_devtools.run_ci_checks import _parse_config

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def test_allotmint_mcp_checks_example_parses():
    path = TEMPLATES_DIR / "allotmint-mcp.cicaid-checks.toml"
    checks = _parse_config(path.read_text(encoding="utf-8"), str(path))
    assert len(checks) >= 1
    assert all(check.name and check.commands for check in checks)
