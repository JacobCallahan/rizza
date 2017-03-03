# -*- encoding: utf-8 -*-
"""A module that provides miscellaneous helper functions."""
from itertools import combinations, product


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
    """Map a tuple of fields to a list of input dictionaries."""
    return [{field: inpt for field, inpt in zip(fields, input_tuple)}
            for input_tuple in input_list]


def dictionary_exclusion(indict=None, exclude=None):
    """Remove any dictionary entries containing the specified string(s)."""
    if exclude:
        if not isinstance(exclude, list):
            exclude = [exclude]
        for exclusion in exclude:
            indict = {x: y for x, y in indict.items() if exclusion not in x}
    return indict
