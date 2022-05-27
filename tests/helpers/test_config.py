# -*- encoding: utf-8 -*-
"""Tests for rizza.helpers.config."""
import os
import pytest
from rizza.helpers import config

BASE_VALUE = "TEST"
BASE_LIST = [1, 2, 3]
BASE_DICT = {'a': 1, 'b': 2, 'c': 3}

def test_positive_create_config():
    """Simply create a config class and check it pulled the default nailgun"""
    test_config = config.Config()
    assert test_config.NAILGUN

def test_positive_load_config():
    """Load the test config and assert the bits are in place"""
    test_config = config.Config(cfg_file='tests/data/test_config.yaml')
    assert test_config.RIZZA['value'] == BASE_VALUE
    assert test_config.RIZZA['list'] == BASE_LIST
    assert test_config.RIZZA['dict'] == BASE_DICT
    assert test_config.NAILGUN['SATUSER'] == 'test_user'
    assert test_config.NAILGUN['VERIFY'] is False

def test_positive_save_config():
    """Verify that we are able to create and save a custom config

    Steps:
        1. Create a new config class instance.
        2. Populate it with constant data.
        3. Save the config to a specific file
        4. Load the saved config into a new instance

    Verify: All saved components match their initial values
    """
    base_config = config.Config()
    base_config.RIZZA['value'] = BASE_VALUE
    base_config.RIZZA['list'] = BASE_LIST
    base_config.RIZZA['dict'] = BASE_DICT
    base_config.save_config('tests/data/base_config.yaml')
    new_config = config.Config(cfg_file='tests/data/base_config.yaml')
    assert new_config.RIZZA['value'] == base_config.RIZZA['value']
    assert new_config.RIZZA['list'] == base_config.RIZZA['list']
    assert new_config.RIZZA['dict'] == base_config.RIZZA['dict']
    os.remove('tests/data/base_config.yaml')

def test_positive_convert_config():
    """Load a yaml config, save it to json, reimport to verify contents"""
    base_config = config.Config(cfg_file='tests/data/test_config.yaml')
    base_config.save_config('tests/data/base_config.json')
    new_config = config.Config(cfg_file='tests/data/base_config.json')
    assert new_config.RIZZA['value'] == base_config.RIZZA['value']
    assert new_config.RIZZA['list'] == base_config.RIZZA['list']
    assert new_config.RIZZA['dict'] == base_config.RIZZA['dict']
    os.remove('tests/data/base_config.json')
