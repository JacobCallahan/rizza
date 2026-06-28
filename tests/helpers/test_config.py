"""Tests for rizza.helpers.config."""
from pathlib import Path
import tempfile

from picoconf import PicoConf
import pytest
import yaml

from rizza.helpers import config

BASE_VALUE = "TEST"
BASE_LIST = [1, 2, 3]
BASE_DICT = {"a": 1, "b": 2, "c": 3}

EXAMPLE_DIR = Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def full_config(tmp_path):
    """Config instance backed by real .pconf files copied from examples."""
    for example in EXAMPLE_DIR.glob("*.pconf.example"):
        dest = tmp_path / example.name.removesuffix(".example")
        dest.write_text(example.read_text())
    return config.Config(cfg_dir=str(tmp_path))


def test_positive_load_config():
    """Load the test config directory and assert the bits are in place"""
    test_config = config.Config(cfg_dir="tests/data/")
    assert test_config.rizza.value == BASE_VALUE
    assert test_config.rizza.list == BASE_LIST
    assert test_config.rizza.dict == BASE_DICT


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
    base_config.rizza.last = last_args
    base_config.save_config()
    assert last_file.exists()
    last_config = PicoConf(str(last_file))
    assert last_config.last.entity == last_args["entity"]
    assert last_config.last.method == last_args["method"]
    last_file.unlink()


def test_positive_defaults_loaded():
    """Verify that DEFAULT_CONFIG values are used when no config file exists"""
    expected_pop_count = config.DEFAULT_CONFIG["genetics"]["population_count"]
    expected_log_level = config.DEFAULT_CONFIG["log_level"]
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = config.Config(cfg_dir=tmpdir)
        assert expected_pop_count == cfg.rizza.genetics.population_count
        assert expected_log_level == cfg.rizza.log_level


def test_positive_picoconf_load():
    """Test loading configuration using picoconf directory format."""
    picoconf_config = config.Config(cfg_dir="tests/data/")
    assert picoconf_config.rizza.value == BASE_VALUE
    assert picoconf_config.rizza.list == BASE_LIST
    assert picoconf_config.rizza.dict == BASE_DICT


def test_get_chunk_full(full_config):
    """get_chunk(None) returns full config dict with top-level keys."""
    result = full_config.get_chunk()
    assert isinstance(result, dict)
    assert "log_level" in result
    assert "genetics" in result
    assert "connection" in result


def test_get_chunk_section(full_config):
    """get_chunk('genetics') returns the genetics sub-dict."""
    result = full_config.get_chunk("genetics")
    assert isinstance(result, dict)
    assert "population_count" in result
    assert result["population_count"] == config.DEFAULT_CONFIG["genetics"]["population_count"]


def test_get_chunk_deep(full_config):
    """get_chunk with a three-level dotted path returns a scalar."""
    result = full_config.get_chunk("genetics.criteria.pass")
    assert result == config.DEFAULT_CONFIG["genetics"]["criteria"]["pass"]


def test_get_chunk_scalar(full_config):
    """get_chunk on a top-level scalar returns the value directly."""
    result = full_config.get_chunk("connection.hostname")
    assert isinstance(result, str)


def test_get_chunk_nonexistent(full_config):
    """get_chunk on a missing key raises KeyError."""
    with pytest.raises(KeyError):
        full_config.get_chunk("nonexistent.key")


def test_set_chunk_imported_file(full_config, tmp_path):
    """set_chunk on a connection key writes only to connection.pconf."""
    full_config.set_chunk("connection.hostname", "new.host.example.com")
    assert full_config.get_chunk("connection.hostname") == "new.host.example.com"
    conn_file = tmp_path / "connection.pconf"
    assert conn_file.exists()
    data = yaml.safe_load(conn_file.read_text())
    assert data["hostname"] == "new.host.example.com"
    rizza_file = tmp_path / "rizza.pconf"
    rizza_data = yaml.safe_load(rizza_file.read_text())
    assert "hostname" not in rizza_data


def test_set_chunk_rizza_file_preserves_import(full_config, tmp_path):
    """set_chunk on a top-level key writes to rizza.pconf and preserves _import."""
    full_config.set_chunk("log_level", "debug")
    rizza_file = tmp_path / "rizza.pconf"
    data = yaml.safe_load(rizza_file.read_text())
    assert data["log_level"] == "debug"
    assert "_import" in data
    assert "genetics.pconf" in data["_import"]


def test_set_chunk_type_coercion(full_config):
    """set_chunk coerces string integers to int via yaml.safe_load."""
    expected = 42
    full_config.set_chunk("genetics.population_count", str(expected))
    assert full_config.get_chunk("genetics.population_count") == expected


def test_init_config_creates_files(tmp_path):
    """init_config copies example files into a fresh directory."""
    cfg = config.Config(cfg_dir=str(tmp_path))
    result = cfg.init_config()
    assert "rizza.pconf" in result["copied"]
    assert (tmp_path / "rizza.pconf").exists()


def test_init_config_skips_existing(tmp_path):
    """init_config skips files that already exist unless force=True."""
    cfg = config.Config(cfg_dir=str(tmp_path))
    cfg.init_config()
    result = cfg.init_config()
    assert result["copied"] == []
    assert len(result["skipped"]) > 0


def test_init_config_force_overwrites(tmp_path):
    """init_config with force=True overwrites existing files."""
    cfg = config.Config(cfg_dir=str(tmp_path))
    cfg.init_config()
    result = cfg.init_config(force=True)
    assert "rizza.pconf" in result["copied"]
    assert result["skipped"] == []
