from cicaid_devtools.lib.issue_review import parse_review_response


def test_parses_title_and_body():
    response = "TITLE: Fix the thing\nBODY:\nDo the work.\nMore detail."
    title, body = parse_review_response(response, "fallback title", "fallback body")
    assert title == "Fix the thing"
    assert body == "Do the work.\nMore detail."


def test_falls_back_when_no_match():
    title, body = parse_review_response("not the expected format", "fallback title", "fallback body")
    assert (title, body) == ("fallback title", "fallback body")


def test_falls_back_when_title_empty():
    response = "TITLE:   \nBODY:\nSome body."
    title, body = parse_review_response(response, "fallback title", "fallback body")
    assert (title, body) == ("fallback title", "fallback body")


def test_falls_back_when_body_empty():
    response = "TITLE: A title\nBODY:\n   "
    title, body = parse_review_response(response, "fallback title", "fallback body")
    assert (title, body) == ("fallback title", "fallback body")
