"""Tests for the redact_env_var_names utility in .github/scripts/review_common.py.

Verifies that:
1. Known env var name patterns (ending in _TOKEN, _KEY, _SECRET, _PASS, _PASSWORD,
   _AUTH, _CREDENTIAL, _API) are redacted.
2. Legitimate non-secret identifiers (MAX_RETRIES, PR_TITLE) are not redacted.
3. Multiple env var names in a single message are all redacted.
4. Edge cases: empty string, no matches, partial matches.
"""

from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path

import pytest

# Import review_common from .github/scripts/ explicitly, avoiding the cached
# src/cicaid_devtools/lib/review_common that earlier tests may have already
# loaded into sys.modules (test_cli.py's importlib.import_module of modules
# that depend on review_common triggers this).
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
_review_common_path = str(_SCRIPTS_DIR / "review_common.py")
_review_common_spec = importlib.util.spec_from_file_location(
    "review_common", _review_common_path
)
review_common = importlib.util.module_from_spec(_review_common_spec)
_review_common_spec.loader.exec_module(review_common)


class TestRedactEnvVarNames:
    """Unit tests for redact_env_var_names."""

    def test_redacts_token_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: GITHUB_TOKEN not set"
        )
        assert "GITHUB_TOKEN" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_key_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: DEEPSEEK_API_KEY not set"
        )
        assert "DEEPSEEK_API_KEY" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_openai_key(self):
        result = review_common.redact_env_var_names(
            "ERROR: OPENAI_API_KEY not set"
        )
        assert "OPENAI_API_KEY" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_secret_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: AWS_SECRET_ACCESS_KEY not set"
        )
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_password_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: DB_PASSWORD is missing"
        )
        assert "DB_PASSWORD" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_pass_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: DB_PASS not configured"
        )
        assert "DB_PASS" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_auth_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: API_AUTH is not set"
        )
        assert "API_AUTH" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_credential_pattern(self):
        result = review_common.redact_env_var_names(
            "ERROR: SERVICE_CREDENTIAL not found"
        )
        assert "SERVICE_CREDENTIAL" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_redacts_api_suffix(self):
        result = review_common.redact_env_var_names(
            "ERROR: SOME_VENDOR_API not set"
        )
        assert "SOME_VENDOR_API" not in result
        assert "[REDACTED_ENV_VAR]" in result

    # ------------------------------------------------------------------
    # Non-secret identifiers must NOT be redacted
    # ------------------------------------------------------------------

    def test_preserves_non_secret_max_retries(self):
        result = review_common.redact_env_var_names(
            "Configuration MAX_RETRIES is set to 5"
        )
        assert "MAX_RETRIES" in result
        assert "[REDACTED_ENV_VAR]" not in result

    def test_preserves_non_secret_pr_title(self):
        result = review_common.redact_env_var_names(
            "The PR_TITLE must be non-empty"
        )
        assert "PR_TITLE" in result
        assert "[REDACTED_ENV_VAR]" not in result

    def test_preserves_followup_llm_provider(self):
        result = review_common.redact_env_var_names(
            "FOLLOWUP_LLM_PROVIDER not set"
        )
        assert "FOLLOWUP_LLM_PROVIDER" in result
        assert "[REDACTED_ENV_VAR]" not in result

    def test_preserves_single_word_identifiers(self):
        result = review_common.redact_env_var_names(
            "The TOKEN was valid"
        )
        # "TOKEN" alone (no underscore prefix) should not match
        assert "TOKEN" in result

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_string(self):
        assert review_common.redact_env_var_names("") == ""

    def test_no_match_returns_unchanged(self):
        original = "Everything is fine, no secrets here."
        assert review_common.redact_env_var_names(original) == original

    def test_multiple_env_vars_in_one_message(self):
        result = review_common.redact_env_var_names(
            "Neither GITHUB_TOKEN nor DEEPSEEK_API_KEY is set"
        )
        assert "GITHUB_TOKEN" not in result
        assert "DEEPSEEK_API_KEY" not in result
        # Both should be replaced, so at least 2 occurrences of placeholder
        assert result.count("[REDACTED_ENV_VAR]") >= 2

    def test_redacts_in_http_error_body(self):
        # Simulate an API error body that references an env var name
        body = '{"error": "DEEPSEEK_API_KEY is invalid"}'
        result = review_common.redact_env_var_names(
            f"ERROR: DeepSeek API returned 401: {body}"
        )
        assert "DEEPSEEK_API_KEY" not in result
        assert "[REDACTED_ENV_VAR]" in result

    def test_preserves_model_names(self):
        # Model names like deepseek-v4-flash are lowercase with hyphens
        result = review_common.redact_env_var_names(
            "Model deepseek-v4-flash not found"
        )
        assert "deepseek-v4-flash" in result

    def test_preserves_snake_case_config(self):
        # snake_case identifiers are not all-caps
        result = review_common.redact_env_var_names(
            "Config deepseek_api_key is missing"
        )
        assert "deepseek_api_key" in result
        assert "[REDACTED_ENV_VAR]" not in result

    def test_preserves_mixed_case(self):
        # Mixed case like GitHub_Token should not match
        result = review_common.redact_env_var_names(
            "The GitHub_Token variable is set"
        )
        assert "GitHub_Token" in result
        assert "[REDACTED_ENV_VAR]" not in result

    # ------------------------------------------------------------------
    # Test that get_required_env redacts the name in stderr
    # ------------------------------------------------------------------

    def test_get_required_env_redacts_name_in_stderr(self, caplog, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        caplog.set_level(logging.ERROR, logger="review_common")

        with pytest.raises(SystemExit) as exc_info:
            review_common.get_required_env("DEEPSEEK_API_KEY")
        assert exc_info.value.code == 1

        # The log message must NOT contain DEEPSEEK_API_KEY
        logged = caplog.text
        assert "DEEPSEEK_API_KEY" not in logged
        assert "[REDACTED_ENV_VAR]" in logged
