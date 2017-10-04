# -*- encoding: utf-8 -*-
"""A module that provides miscellaneous helper functions."""
from itertools import combinations, product
from json import loads
from requests import HTTPError
from nailgun import entity_mixins


def combination_list(base=None, max_fields=None):
    """Create a list of all combinations from the source list."""
    if not base:
        return []

    if not max_fields:
        max_fields = len(base)

    combo_list = []
    for _ in range(1, max_fields + 1):
        combo_list.extend(
            [combo for combo in combinations(base, _)])

    return combo_list


def product_list(base=None, max_fields=None):
    """Create a list of all products from the source list."""
    if not base or max_fields == 0:
        return []

    if not max_fields:
        max_fields = len(base)

    return [_ for _ in product(base, repeat=max_fields)]


def map_field_inputs(fields, input_list):
    """Map a tuple of fields to a list of input tuples."""
    return [{field: inpt for field, inpt in zip(fields, input_tupe)}
            for input_tupe in input_list]


def dictionary_exclusion(indict=None, exclude=None):
    """Remove any dictionary entries containing the specified string(s)."""
    if exclude:
        if not isinstance(exclude, list):
            exclude = [exclude]
        for exclusion in exclude:
            exclusion = str(exclusion)
            indict = {
                x: y for x, y
                in indict.items()
                if exclusion not in str(x)
                and exclusion not in str(y)
            }
    return indict


def handle_exception(exception=None):
    """Translate an exception into a usable format."""
    if exception.__class__.__name__ in dir(entity_mixins):
        return {'nailgun': exception.__class__.__name__}
    elif isinstance(exception, HTTPError):
        return {'HTTPError': {
            name: contents for name, contents
            in exception.__dict__.items() if '_' not in name
        }}
    elif 'args' in dir(exception):
        return {exception.__class__.__name__: exception.args}
    else:
        return {'unhandled': str(exception) or 'undefined'}


def json_serial(obj=None):
    """JSON serializer for objects not serializable by default json code."""
    if 'datetime' in str(obj.__class__):
        return obj.isoformat()
    elif obj.__class__.__name__ == 'PreparedRequest':
        return loads(obj.body)
    elif obj.__class__.__name__ == 'Response':
        return {'message': obj.json(), 'status': obj.status_code}
    raise TypeError("Type {0} not serializable".format(type(obj)))


def dict_search(needle, haystack):
    if not isinstance(haystack, dict):
        if str(needle) in str(haystack):
            return True
        else:
            return False
    if needle in haystack:
        return True
    for key, value in haystack.items():
        if isinstance(value, dict):
            dict_search(needle, value)
        else:
            if str(needle) in str(haystack):
                return True
    return False
