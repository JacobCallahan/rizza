# -*- encoding: utf-8 -*-
"""Tests for rizza.helpers.text."""
import pytest
from rizza.helpers.text import *

LONG_STRING = 'I am a larger haystack in which to find a needle!'


def test_positive_similarity():
    assert similarity(term1='needle', term2='needle') == 1.0


def test_positive_similarity_far():
    assert similarity(term1='needle', term2='asdf') == 0.2


def test_negative_similarity():
    assert similarity(term1='needle', term2='NEEDLE') == 0.0


def test_positive_fuzzyfind():
    assert fuzzyfind(needle='needle', haystack=LONG_STRING)


def test_positive_fuzzyfind_threshold():
    assert fuzzyfind(
        needle='boy', haystack=LONG_STRING, threshold=0.4)


def test_negative_fuzzyfind():
    assert not fuzzyfind(needle='boy', haystack=LONG_STRING)


def test_positive_fuzzyfind_threshold():
    assert not fuzzyfind(
        needle='boy', haystack=LONG_STRING, threshold=0.5)


def test_positive_pmatch():
    result = pmatch(needle='needle', haystack=LONG_STRING)
    assert result[0]  # string was found
    assert result[1] == 42  # string start location


def test_positive_pmatch_threshold():
    result = pmatch(
        needle='boy', haystack=LONG_STRING, threshold=0.4)
    assert result[0]  # string was found
    assert result[1] == 7  # string start location


def test_negative_pmatch():
    assert not pmatch(needle='boy', haystack=LONG_STRING)[0]


def test_positive_pmatch_threshold():
    assert not pmatch(
        needle='boy', haystack=LONG_STRING, threshold=0.5)[0]
