"""Tests for rizza.helpers.misc."""
from rizza.helpers import misc

TEST_DICT = {1: 2, "3": "4", "five": [6, "7", "eight"], 9: {10: "eleven"}}


def test_positive_dictionary_exclusion():
    assert misc.dictionary_exclusion(indict=TEST_DICT, exclude="ve") == {1: 2, "3": "4"}


def test_positive_dictionary_exclusion_empty():
    assert misc.dictionary_exclusion(indict=TEST_DICT) == TEST_DICT


def test_positive_dict_search_int():
    assert misc.dict_search(1, TEST_DICT)


def test_positive_dict_search_str():
    assert misc.dict_search("4", TEST_DICT)


def test_positive_dict_search_nested_list():
    assert misc.dict_search("eight", TEST_DICT)


def test_positive_dict_search_nested_dict():
    assert misc.dict_search("eleven", TEST_DICT)


def test_negative_dict_search_int():
    assert not misc.dict_search(18, TEST_DICT)
