# -*- encoding: utf-8 -*-
"""Tests for rizza.helpers.misc."""
import pytest
from rizza.helpers.misc import *


TEST_DICT = {1: 2, '3': '4', 'five': [6, '7', 'eight'], 9: {10: 'eleven'}}

def test_positive_combination_list():
    assert combination_list(base=[1, 2, 3]) == [
        (1,), (2,), (3,), (1, 2), (1, 3), (2, 3), (1, 2, 3)
    ]


def test_positive_combination_list_max_fields():
    assert combination_list(base=[1, 2, 3], max_fields=2) == [
        (1,), (2,), (3,), (1, 2), (1, 3), (2, 3)
    ]


def test_positive_combination_list_empty():
    assert combination_list() == []


def test_positive_product_list():
    assert product_list(base=[1, 2]) == [
        (1, 1), (1, 2), (2, 1), (2, 2)
    ]


def test_positive_product_list_max_fields():
    assert product_list(base=[1, 2, 3], max_fields=2) == [
        (1, 1), (1, 2), (1, 3), (2, 1), (2, 2),
        (2, 3), (3, 1), (3, 2), (3, 3)
    ]


def test_positive_product_list_empty():
    assert product_list() == []


def test_positive_map_field_inputs():
    assert map_field_inputs(
        (1, 2, 3), [(4, 5), (6, 7), (8, 9)]) == [
            {1: 4, 2: 5}, {1: 6, 2: 7}, {1: 8, 2: 9}
        ]


def test_positive_dictionary_exclusion():
    assert dictionary_exclusion(
        indict=TEST_DICT, exclude='ve') == {1: 2, '3': '4'}


def test_positive_dictionary_exclusion_empty():
    assert dictionary_exclusion(indict=TEST_DICT) == TEST_DICT


def test_positive_dict_search_int():
    assert dict_search(1, TEST_DICT)


def test_positive_dict_search_str():
    assert dict_search('4', TEST_DICT)


def test_positive_dict_search_nested_list():
    assert dict_search('eight', TEST_DICT)


def test_positive_dict_search_nested_dict():
    assert dict_search('eleven', TEST_DICT)


def test_negative_dict_search_int():
    assert not dict_search(18, TEST_DICT)
