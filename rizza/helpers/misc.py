"""A module that provides miscellaneous helper functions."""
from inspect import signature
from json import loads
import logging
from random import randint

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
        return str(needle) in str(haystack)
    if needle in haystack:
        return True
    for key, value in haystack.items():
        if str(needle) in str(key):
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
    if "genetic" in name:
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
