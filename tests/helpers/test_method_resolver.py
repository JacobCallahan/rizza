"""Tests for rizza.helpers.method_resolver."""
from pathlib import Path
import tempfile

import pytest
import yaml

from rizza.helpers import config
from rizza.helpers.method_resolver import get_explored_methods, get_new_methods, resolve_methods

_EXAMPLE_DIR = Path(__file__).parent.parent.parent / "config"


# Dummy entity and method callables for testing
def _fake_create():
    pass


def _fake_update():
    pass


_FAKE_ENTITY_CLS = type("FakeEntity", (), {"create": _fake_create, "update": _fake_update})
_ALL_METHODS = {"create": _fake_create, "update": _fake_update}


@pytest.fixture(scope="module")
def conf():
    with tempfile.TemporaryDirectory() as tmpdir:
        for ex in _EXAMPLE_DIR.glob("*.pconf.example"):
            (Path(tmpdir) / ex.name.removesuffix(".example")).write_text(ex.read_text())
        yield config.Config(cfg_dir=tmpdir)


@pytest.fixture
def data_dir(conf):
    """Create a temp genetic_tests dir; clean the FakeEntity file before and after each test."""
    d = conf.base_dir / "data" / "genetic_tests"
    d.mkdir(parents=True, exist_ok=True)
    entity_file = d / "FakeEntity.yaml"
    entity_file.unlink(missing_ok=True)
    yield d
    entity_file.unlink(missing_ok=True)


def _write_entity_file(data_dir, entity_name, tests: dict):
    f = data_dir / f"{entity_name}.yaml"
    yaml.dump(tests, f.open("w"))
    return f


def test_get_new_methods_no_file(conf, data_dir, monkeypatch):
    """All methods are new when there is no saved test file."""
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = get_new_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS)
    assert set(result.keys()) == {"create", "update"}


def test_get_new_methods_partial(conf, data_dir, monkeypatch):
    """Only methods without a saved positive test are returned."""
    _write_entity_file(
        data_dir,
        "FakeEntity",
        {"FakeEntity create positive": {"arg_dict": {"name": "gen_string"}}},
    )
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = get_new_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS)
    assert "create" not in result
    assert "update" in result


def test_get_new_methods_all_explored(conf, data_dir, monkeypatch):
    """Empty dict returned when all methods are already saved."""
    _write_entity_file(
        data_dir,
        "FakeEntity",
        {
            "FakeEntity create positive": {"arg_dict": {}},
            "FakeEntity update positive": {"arg_dict": {}},
        },
    )
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = get_new_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS)
    assert result == {}


def test_get_new_methods_seek_bad(conf, data_dir, monkeypatch):
    """seek_bad=True checks for negative tests."""
    _write_entity_file(
        data_dir,
        "FakeEntity",
        {"FakeEntity create negative": {"arg_dict": {}}},
    )
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = get_new_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS, seek_bad=True)
    assert "create" not in result
    assert "update" in result


def test_get_explored_methods(conf, data_dir, monkeypatch):
    """Only methods with a saved positive test are returned."""
    _write_entity_file(
        data_dir,
        "FakeEntity",
        {"FakeEntity create positive": {"arg_dict": {}}},
    )
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = get_explored_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS)
    assert "create" in result
    assert "update" not in result


def test_resolve_methods_all(conf, data_dir, monkeypatch):
    """_all returns every method."""
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = resolve_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS, "_all")
    assert set(result.keys()) == {"create", "update"}


def test_resolve_methods_new(conf, data_dir, monkeypatch):
    """_new delegates to get_new_methods."""
    _write_entity_file(
        data_dir,
        "FakeEntity",
        {"FakeEntity create positive": {"arg_dict": {}}},
    )
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = resolve_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS, "_new")
    assert "create" not in result
    assert "update" in result


def test_resolve_methods_specific(conf, data_dir, monkeypatch):
    """A specific method name returns just that method."""
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = resolve_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS, "create")
    assert list(result.keys()) == ["create"]


def test_resolve_methods_specific_missing(conf, data_dir, monkeypatch):
    """A specific method name not found returns empty dict."""
    monkeypatch.setattr(
        "rizza.helpers.method_resolver.EntityTester.pull_methods",
        lambda _entity: _ALL_METHODS,
    )
    result = resolve_methods(conf, "FakeEntity", _FAKE_ENTITY_CLS, "destroy")
    assert result == {}
