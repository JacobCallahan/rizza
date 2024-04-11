"""Tests for rizza.helpers.text."""
from rizza.helpers import text

LONG_STRING = "I am a larger haystack in which to find a needle!"

# ruff: noqa: PLR2004


def test_similarity():
    assert text.similarity(term1="needle", term2="needle") == 1.0


def test_similarity_far():
    assert text.similarity(term1="needle", term2="asdf") == 0.2


def test_negative_similarity():
    assert text.similarity(term1="needle", term2="NEEDLE") == 0.0


def test_fuzzyfind():
    assert text.fuzzyfind(needle="needle", haystack=LONG_STRING)


def test_fuzzyfind_threshold():
    assert text.fuzzyfind(needle="boy", haystack=LONG_STRING, threshold=0.4)


def test_negative_fuzzyfind():
    assert not text.fuzzyfind(needle="boy", haystack=LONG_STRING)


def test_pmatch():
    result = text.pmatch(needle="needle", haystack=LONG_STRING)
    assert result[0]  # string was found
    assert result[1] == 42  # string start location


def test_pmatch_threshold():
    result = text.pmatch(needle="boy", haystack=LONG_STRING, threshold=0.4)
    assert result[0]  # string was found
    assert result[1] == 7  # string start location


def test_negative_pmatch():
    assert not text.pmatch(needle="boy", haystack=LONG_STRING)[0]


def test_cutoff_pmatch_threshold():
    assert not text.pmatch(needle="boy", haystack=LONG_STRING, threshold=0.5)[0]
