from unittest.mock import MagicMock, patch

from cicaid_devtools.lib import github_issue_create


def _response(status_code, headers=None, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = github_issue_create.requests.HTTPError(
            f"{status_code} error", response=resp
        )
    else:
        resp.raise_for_status.side_effect = None
    return resp


def test_create_issue_via_api_succeeds_on_first_try():
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/1"})

    with patch.object(github_issue_create.requests, "post", return_value=success) as post:
        result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/1"
    post.assert_called_once()


def test_create_issue_via_api_retries_on_429_then_succeeds():
    limited = _response(429, headers={"Retry-After": "0"})
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/2"})

    with patch.object(github_issue_create.requests, "post", side_effect=[limited, success]):
        with patch.object(github_issue_create.time, "sleep") as sleep:
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/2"
    sleep.assert_called_once_with(0.0)


def test_create_issue_via_api_ignores_negative_retry_after():
    """A malformed negative Retry-After must not reach time.sleep() (which
    raises ValueError on a negative value) -- fall back to exponential
    backoff instead."""
    limited = _response(429, headers={"Retry-After": "-1"})
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/5"})

    with patch.object(github_issue_create.requests, "post", side_effect=[limited, success]):
        with patch.object(github_issue_create.time, "sleep") as sleep:
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/5"
    sleep.assert_called_once_with(1)


def test_create_issue_via_api_caps_oversized_retry_after():
    limited = _response(429, headers={"Retry-After": "600"})
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/6"})

    with patch.object(github_issue_create.requests, "post", side_effect=[limited, success]):
        with patch.object(github_issue_create.time, "sleep") as sleep:
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/6"
    sleep.assert_called_once_with(github_issue_create._MAX_RETRY_AFTER_SECONDS)


def test_create_issue_via_api_retries_on_403_with_exhausted_rate_limit():
    limited = _response(403, headers={"X-RateLimit-Remaining": "0"})
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/3"})

    with patch.object(github_issue_create.requests, "post", side_effect=[limited, success]):
        with patch.object(github_issue_create.time, "sleep"):
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/3"


def test_create_issue_via_api_does_not_retry_plain_403():
    """A 403 that isn't a rate limit (e.g. missing permissions) must fail
    immediately, not be treated as a rate-limit retry candidate."""
    forbidden = _response(403, headers={})

    with patch.object(github_issue_create.requests, "post", return_value=forbidden) as post:
        with patch.object(github_issue_create.time, "sleep") as sleep:
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result is None
    post.assert_called_once()
    sleep.assert_not_called()


def test_create_issue_via_api_gives_up_after_max_retries():
    limited = _response(429, headers={})

    with patch.object(github_issue_create.requests, "post", return_value=limited) as post:
        with patch.object(github_issue_create.time, "sleep"):
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result is None
    assert post.call_count == github_issue_create.MAX_RATE_LIMIT_RETRIES + 1


def test_create_issue_via_api_uses_exponential_backoff_without_retry_after():
    limited = _response(429, headers={})
    success = _response(201, json_data={"html_url": "https://github.com/o/r/issues/4"})

    responses = [limited, limited, success]
    with patch.object(github_issue_create.requests, "post", side_effect=responses):
        with patch.object(github_issue_create.time, "sleep") as sleep:
            result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result == "https://github.com/o/r/issues/4"
    assert sleep.call_args_list[0].args[0] == 1
    assert sleep.call_args_list[1].args[0] == 2


def test_create_issue_via_api_handles_request_exception():
    with patch.object(
        github_issue_create.requests,
        "post",
        side_effect=github_issue_create.requests.RequestException("boom"),
    ):
        result = github_issue_create.create_issue_via_api("o", "r", "t", "b", [], "tok")

    assert result is None


def test_create_issue_via_api_signature_unchanged():
    """Regression guard: rate-limit handling must not add/remove parameters."""
    import inspect

    params = list(inspect.signature(github_issue_create.create_issue_via_api).parameters)
    assert params == ["owner", "repo", "title", "body", "labels", "token"]
