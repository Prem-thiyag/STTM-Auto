import pytest

from engine.utils import find_matching_brace, now_iso, sha256_of_text


def test_find_matching_brace_simple() -> None:
    text = "config {}"
    assert find_matching_brace(text, 7) == 8


def test_find_matching_brace_nested() -> None:
    text = 'config {"a": {"b": 1}}'
    open_index = text.index("{")
    assert find_matching_brace(text, open_index) == len(text) - 1


def test_find_matching_brace_ignores_braces_in_strings() -> None:
    text = 'config {"note": "a } inside a string"}'
    open_index = text.index("{")
    assert find_matching_brace(text, open_index) == len(text) - 1


def test_find_matching_brace_unbalanced_raises() -> None:
    with pytest.raises(ValueError, match="unbalanced"):
        find_matching_brace("config {\"a\": 1", 7)


def test_find_matching_brace_wrong_start_index_raises() -> None:
    with pytest.raises(ValueError, match="not an opening brace"):
        find_matching_brace("config {}", 0)


def test_sha256_of_text_is_deterministic_and_prefixed() -> None:
    h1 = sha256_of_text("SELECT 1;")
    h2 = sha256_of_text("SELECT 1;")
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert sha256_of_text("SELECT 2;") != h1


def test_now_iso_format() -> None:
    ts = now_iso()
    assert ts.endswith("Z")
    assert "T" in ts
