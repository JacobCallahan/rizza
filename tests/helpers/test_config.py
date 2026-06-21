"""Tests for rizza.helpers.config."""
from pathlib import Path
import tempfile

from picoconf import PicoConf

from rizza.helpers import config

BASE_VALUE = "TEST"
BASE_LIST = [1, 2, 3]
BASE_DICT = {"a": 1, "b": 2, "c": 3}


def test_positive_load_config():
    """Load the test config directory and assert the bits are in place"""
    test_config = config.Config(cfg_dir="tests/data/")
    assert test_config.RIZZA.value == BASE_VALUE
    assert test_config.RIZZA.list == BASE_LIST
    assert test_config.RIZZA.dict == BASE_DICT


def test_positive_save_last():
    """Verify that LAST command arguments are saved to last.pconf

    Steps:
        1. Create a new config class instance.
        2. Set a LAST value.
        3. Save the config (writes last.pconf).
        4. Load last.pconf independently and verify contents.

    Verify: LAST contents match what was saved
    """
    last_file = Path("tests/data/last.pconf")
    base_config = config.Config(cfg_dir="tests/data/")
    last_args = {"entity": "Product", "method": "create"}
    base_config.RIZZA.LAST = last_args
    base_config.save_config()
    assert last_file.exists()
    last_config = PicoConf(str(last_file))
    assert last_config.LAST.entity == last_args["entity"]
    assert last_config.LAST.method == last_args["method"]
    last_file.unlink()


def test_positive_defaults_loaded():
    """Verify that DEFAULT_CONFIG values are used when no config file exists"""
    expected_pop_count = config.DEFAULT_CONFIG["rizza"]["GENETICS"]["POPULATION_COUNT"]
    expected_log_level = config.DEFAULT_CONFIG["rizza"]["LOG_LEVEL"]
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = config.Config(cfg_dir=tmpdir)
        assert expected_pop_count == cfg.RIZZA.GENETICS.POPULATION_COUNT
        assert expected_log_level == cfg.RIZZA.LOG_LEVEL


def test_positive_picoconf_load():
    """Test loading configuration using picoconf directory format."""
    picoconf_config = config.Config(cfg_dir="tests/data/")
    assert picoconf_config.RIZZA.value == BASE_VALUE
    assert picoconf_config.RIZZA.list == BASE_LIST
    assert picoconf_config.RIZZA.dict == BASE_DICT
