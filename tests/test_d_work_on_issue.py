from cicaid_devtools.d_work_on_issue import slugify


def test_slugify_normal_title():
    assert slugify("Fix the login bug") == "fix-the-login-bug"


def test_slugify_truncates_to_50_chars():
    assert len(slugify("x " * 60)) <= 50


def test_slugify_never_ends_in_hyphen():
    assert not slugify("Trailing punctuation!!!").endswith("-")


def test_slugify_falls_back_to_hash_for_emoji_only_title():
    slug = slugify("🎉🎉🎉")
    assert slug != ""
    assert all(c in "0123456789abcdef" for c in slug)
    assert len(slug) == 8


def test_slugify_is_deterministic_for_hash_fallback():
    assert slugify("🎉🎉🎉") == slugify("🎉🎉🎉")
