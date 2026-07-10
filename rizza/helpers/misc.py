"""A module that provides miscellaneous helper functions."""
from inspect import signature
from json import loads
import logging
from random import randint
import re

from requests import HTTPError

logger = logging.getLogger(__name__)


def dictionary_exclusion(indict=None, exclude=None):
    """Remove any dictionary entries containing the specified string(s)."""
    if exclude:
        if not isinstance(exclude, list):
            exclude = [exclude]
        for exclusion in exclude:
            _exclusion = str(exclusion)
            indict = {
                x: y
                for x, y in indict.items()
                if _exclusion not in str(x) and _exclusion not in str(y)
            }
    return indict


def extract_validation_errors(fail_data):
    """Extract field-level validation errors from an HTTPError fail dict.

    Navigates the structure produced by handle_exception() to find
    field-to-messages mappings from API validation responses (typically 422).

    Handles common API patterns:
    - Standard: {"errors": {"field": ["msg1", "msg2"]}}
    - Singular: {"error": {"field": ["msg"]}}
    - FastAPI:  {"detail": [{"loc": ["body", "field"], "msg": "..."}]}

    Returns dict mapping field names to lists of error message strings,
    or empty dict if no validation errors found.
    """
    if not isinstance(fail_data, dict):
        return {}

    http_data = fail_data.get("HTTPError")
    if not isinstance(http_data, dict):
        return {}

    response_data = http_data.get("response")
    if not isinstance(response_data, dict):
        return {}

    # Standard pattern: {"errors": {"field": ["msg1", ...]}}
    errors = response_data.get("errors")
    if isinstance(errors, dict):
        result = {}
        for field, messages in errors.items():
            if isinstance(messages, list):
                result[field] = [str(m) for m in messages]
            elif isinstance(messages, str):
                result[field] = [messages]
        if result:
            return result

    # Singular pattern: {"error": {"field": ["msg"]}}
    error = response_data.get("error")
    if isinstance(error, dict):
        result = {}
        for field, messages in error.items():
            if isinstance(messages, list):
                result[field] = [str(m) for m in messages]
            elif isinstance(messages, str):
                result[field] = [messages]
        if result:
            return result

    # FastAPI pattern: {"detail": [{"loc": ["body", "field"], "msg": "..."}]}
    detail = response_data.get("detail")
    if isinstance(detail, list):
        result = {}
        for item in detail:
            if not isinstance(item, dict):
                continue
            loc = item.get("loc")
            msg = item.get("msg")
            if not loc or not msg:
                continue
            field = str(loc[-1]) if loc else None
            if field:
                result.setdefault(field, []).append(str(msg))
        if result:
            return result

    return {}


_MISSING_PARAM_RE = re.compile(r"missing \d+ required (?:positional )?arguments?:")


def extract_missing_params(fail_data):
    """Extract parameter names from TypeError 'missing required argument' messages.

    Parses Python's deterministic TypeError format:
    - "Cls.__init__() missing 1 required positional argument: 'name'"
    - "Cls.__init__() missing 3 required positional arguments: 'a', 'b', and 'c'"

    Returns list of param name strings, or empty list if not applicable.
    """
    if not isinstance(fail_data, dict):
        return []

    type_error = fail_data.get("TypeError")
    if not type_error:
        return []

    msg = str(type_error[0]) if isinstance(type_error, list | tuple) and type_error else ""
    if not _MISSING_PARAM_RE.search(msg):
        return []

    after_colon = msg.split(":", 1)[-1] if ":" in msg else ""
    return re.findall(r"'(\w+)'", after_colon)


def handle_exception(exception=None):
    """Translate an exception into a usable format."""
    if isinstance(exception, HTTPError):
        resp = {}
        for name, contents in exception.__dict__.items():
            if "_" not in name:
                if "json" in dir(contents):
                    try:
                        resp[name] = contents.json()
                    except Exception:
                        resp[name] = contents.content
                else:
                    resp[name] = contents
        return {"HTTPError": resp}
    if "args" in dir(exception):
        return {exception.__class__.__name__: exception.args}
    return {"unhandled": str(exception) or "undefined"}


def json_serial(obj=None):
    """JSON serializer for objects not serializable by default json code."""
    if "datetime" in str(obj.__class__):
        return obj.isoformat()
    if obj.__class__.__name__ == "PreparedRequest":
        return loads(obj.body)
    if obj.__class__.__name__ == "Response":
        return {"message": obj.json(), "status": obj.status_code}
    if obj.__class__.__name__ == "PosixPath":
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def dict_search(needle, haystack):
    if not isinstance(haystack, dict):
        if isinstance(haystack, list | tuple):
            return any(dict_search(needle, item) for item in haystack)
        return str(needle) == str(haystack)
    if needle in haystack:
        return True
    for key, value in haystack.items():
        if str(needle) == str(key):
            return True
        if dict_search(needle, value):
            return True
    return False


def field_to_entity(field, field_info=None):
    """Takes in a field name and tries to find an entity that matches.

    :param field_info: Optional parsed annotation dict. If it contains an 'entity'
        key, that entity name is returned directly instead of guessing.
    """
    if field_info and field_info.get("entity"):
        return field_info["entity"]

    from rizza.entity_tester import EntityTester

    entity_list = EntityTester.pull_entities().keys()
    field = "".join([x.capitalize() for x in field.split("_")])
    if field in entity_list:
        return field


def get_default_type(func):
    """Return the type of the first default argument for a function or None"""
    parameters = signature(func).parameters
    return [type(parameters[key].default) for key in parameters if parameters[key].default]


def form_input(name, methods, field, config, field_info=None):
    """Take in a function name, get information, call it, return result"""
    if "genetic" in name or name == "get_entity_id":
        entity = field_to_entity(field, field_info)
        if entity:
            return methods.get(name, lambda: name)(config, entity)
        return "~"
    types = get_default_type(methods.get(name, lambda: name))
    if types and types[0] == int and types.count(types[0]) == len(types):
        # currently only support integers
        for i in range(len(types)):
            types[i] = randint(1, 20)
        try:
            return methods.get(name, lambda: name)(*types)
        except Exception as err:
            logger.debug(err)
    return methods.get(name, lambda: name)()
