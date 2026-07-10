"""Helpers for resolving which methods to explore or validate."""
import contextlib

import yaml

from rizza.entity_tester import EntityTester


def get_new_methods(config, entity_name, entity_cls, seek_bad=False):
    """Return methods that don't yet have a saved passing test for this entity.

    :param config: Config instance.
    :param entity_name: String entity name.
    :param entity_cls: Entity class from apix module.
    :param seek_bad: If True, checks for missing negative tests instead of positive.
    :returns: Dict of {method_name: method_callable} not yet saved.
    """
    mode = "negative" if seek_bad else "positive"
    test_file = config.base_dir / "data" / "genetic_tests" / f"{entity_name}.yaml"
    saved_keys = set()
    if test_file.exists():
        with contextlib.suppress(Exception):
            saved_keys = set((yaml.safe_load(test_file.read_text()) or {}).keys())
    all_methods = EntityTester.pull_methods(entity_cls)
    return {
        name: method
        for name, method in all_methods.items()
        if f"{entity_name} {name} {mode}" not in saved_keys
    }


def get_explored_methods(config, entity_name, entity_cls, seek_bad=False):
    """Return methods that already have a saved passing test for this entity.

    :param config: Config instance.
    :param entity_name: String entity name.
    :param entity_cls: Entity class from apix module.
    :param seek_bad: If True, checks for existing negative tests instead of positive.
    :returns: Dict of {method_name: method_callable} already saved.
    """
    mode = "negative" if seek_bad else "positive"
    test_file = config.base_dir / "data" / "genetic_tests" / f"{entity_name}.yaml"
    saved_keys = set()
    if test_file.exists():
        with contextlib.suppress(Exception):
            saved_keys = set((yaml.safe_load(test_file.read_text()) or {}).keys())
    all_methods = EntityTester.pull_methods(entity_cls)
    return {
        name: method
        for name, method in all_methods.items()
        if f"{entity_name} {name} {mode}" in saved_keys
    }


def resolve_methods(config, entity_name, entity_cls, method_mode, seek_bad=False):
    """Resolve a method mode string to a dict of methods to run.

    :param config: Config instance.
    :param entity_name: String entity name.
    :param entity_cls: Entity class from apix module.
    :param method_mode: "_new", "_all", or a specific method name.
    :param seek_bad: Passed through to get_new_methods when method_mode is "_new".
    :returns: Dict of {method_name: method_callable}.
    """
    if method_mode == "_new":
        return get_new_methods(config, entity_name, entity_cls, seek_bad)
    if method_mode == "_all":
        return EntityTester.pull_methods(entity_cls)
    methods = EntityTester.pull_methods(entity_cls)
    if method_mode in methods:
        return {method_mode: methods[method_mode]}
    return {}
