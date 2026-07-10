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


def test_dict_search_no_substring_match_key():
    assert not misc.dict_search("pass", {"fail": {"password": "secret"}})


def test_dict_search_no_substring_match_value():
    assert not misc.dict_search("200", {"code": 1200})


def test_dict_search_exact_int_value():
    assert misc.dict_search("200", {"code": 200})


# ── extract_validation_errors ────────────────────────────────────────────────


def test_extract_validation_standard_errors():
    fail_data = {
        "HTTPError": {
            "response": {
                "errors": {
                    "label": ["cannot contain special characters", "too long"],
                    "name": ["is required"],
                }
            }
        }
    }
    result = misc.extract_validation_errors(fail_data)
    assert result == {
        "label": ["cannot contain special characters", "too long"],
        "name": ["is required"],
    }


def test_extract_validation_singular_error():
    fail_data = {"HTTPError": {"response": {"error": {"name": ["can't be blank"]}}}}
    assert misc.extract_validation_errors(fail_data) == {"name": ["can't be blank"]}


def test_extract_validation_fastapi_detail():
    fail_data = {
        "HTTPError": {
            "response": {
                "detail": [
                    {"loc": ["body", "email"], "msg": "invalid format"},
                ]
            }
        }
    }
    assert misc.extract_validation_errors(fail_data) == {"email": ["invalid format"]}


def test_extract_validation_no_errors():
    assert misc.extract_validation_errors({"HTTPError": {"response": {}}}) == {}
    assert misc.extract_validation_errors({}) == {}
    assert misc.extract_validation_errors({"TypeError": "bad"}) == {}


def test_extract_validation_string_message():
    fail_data = {"HTTPError": {"response": {"errors": {"field": "single msg"}}}}
    assert misc.extract_validation_errors(fail_data) == {"field": ["single msg"]}


# ── extract_missing_params ──────────────────────────────────────────────────


def test_extract_missing_params_single():
    fail_data = {
        "TypeError": ("Organization.__init__() missing 1 required positional argument: 'name'",)
    }
    assert misc.extract_missing_params(fail_data) == ["name"]


def test_extract_missing_params_multiple():
    fail_data = {
        "TypeError": (
            "JobTemplate.__init__() missing 3 required positional arguments: "
            "'name', 'job_category', and 'provider_type'",
        )
    }
    assert misc.extract_missing_params(fail_data) == ["name", "job_category", "provider_type"]


def test_extract_missing_params_method():
    fail_data = {
        "TypeError": (
            "Organization.update() missing 1 required positional argument: 'organization'",
        )
    }
    assert misc.extract_missing_params(fail_data) == ["organization"]


def test_extract_missing_params_not_type_error():
    assert misc.extract_missing_params({"HTTPError": {"response": {}}}) == []
    assert misc.extract_missing_params({"Exception": ("something else",)}) == []
    assert misc.extract_missing_params({}) == []


def test_extract_missing_params_non_missing_type_error():
    fail_data = {"TypeError": ("unexpected type for argument 'name'",)}
    assert misc.extract_missing_params(fail_data) == []
