"""Tests for rizza.entity_tester."""
from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

from rizza.entity_tester import EntityTester, EntityTestTask

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_mock_module():
    """Create a minimal fake apix module for testing."""
    mock_module = MagicMock()

    class FakeSatellite:
        pass

    class FakeOrganization(FakeSatellite):
        _api_methods: ClassVar[list[str]] = ["create", "index"]

        def create(self, name: str, description: str | None = None):
            pass

        def index(self):
            pass

    mock_module.Satellite = FakeSatellite
    mock_module.APIConnection = MagicMock()
    mock_module.FakeOrganization = FakeOrganization

    # Make inspect.getmembers return the fake classes
    mock_module.__dict__ = {
        "Satellite": FakeSatellite,
        "FakeOrganization": FakeOrganization,
        "APIConnection": MagicMock(),
    }
    return mock_module, FakeSatellite, FakeOrganization


# ---------------------------------------------------------------------------
# pull_entities tests
# ---------------------------------------------------------------------------


def test_pull_entities_no_module():
    """Returns empty dict gracefully when apix module is not available."""
    with patch("rizza.apix_loader.get_apix_module", side_effect=FileNotFoundError("not found")):
        result = EntityTester.pull_entities()
    assert result == {}


def test_pull_entities_with_module():
    """Returns entity classes discovered from the apix module."""
    mock_module, FakeSatellite, FakeOrganization = _make_mock_module()

    with (
        patch("rizza.apix_loader.get_apix_module", return_value=mock_module),
        patch("rizza.apix_loader.get_satellite_class", return_value=FakeSatellite),
        patch(
            "inspect.getmembers",
            return_value=[
                ("Satellite", FakeSatellite),
                ("FakeOrganization", FakeOrganization),
            ],
        ),
    ):
        result = EntityTester.pull_entities()

    assert "FakeOrganization" in result
    assert "Satellite" not in result


# ---------------------------------------------------------------------------
# pull_methods tests
# ---------------------------------------------------------------------------


def test_pull_methods_none_entity():
    """Returns empty dict when entity is None."""
    result = EntityTester.pull_methods(None)
    assert result == {}


def test_pull_methods_with_api_methods():
    """Uses _api_methods list when available."""
    _, FakeSatellite, FakeOrganization = _make_mock_module()

    with (
        patch("rizza.apix_loader.get_apix_module"),
        patch("rizza.apix_loader.get_satellite_class", return_value=FakeSatellite),
    ):
        result = EntityTester.pull_methods(FakeOrganization)

    assert "create" in result
    assert "index" in result
    assert callable(result["create"])


def test_pull_methods_excludes():
    """Applies exclude filter to methods."""
    _, FakeSatellite, FakeOrganization = _make_mock_module()

    with (
        patch("rizza.apix_loader.get_apix_module"),
        patch("rizza.apix_loader.get_satellite_class", return_value=FakeSatellite),
    ):
        result = EntityTester.pull_methods(FakeOrganization, exclude=["create"])

    assert "create" not in result
    assert "index" in result


# ---------------------------------------------------------------------------
# pull_fields tests
# ---------------------------------------------------------------------------


def test_pull_fields_none_entity():
    """Returns empty dict when entity is None."""
    result = EntityTester.pull_fields(None)
    assert result == {}


def test_pull_fields_parses_annotations():
    """Parses method annotations into field_info dicts."""
    _, FakeSatellite, FakeOrganization = _make_mock_module()

    result = EntityTester.pull_fields(FakeOrganization, method="create")

    assert "name" in result
    assert result["name"]["type"] == "str"


# ---------------------------------------------------------------------------
# pull_args tests
# ---------------------------------------------------------------------------


def test_pull_args_none_method():
    """Returns None when method is None."""
    result = EntityTester.pull_args(None)
    assert result is None


def test_pull_args_real_function():
    """Returns parameter names for a real callable, excluding 'self'."""

    def sample(self, foo: str, bar: int = 0):
        pass

    result = EntityTester.pull_args(sample)
    assert result == ["foo", "bar"]


# ---------------------------------------------------------------------------
# pull_input_methods tests
# ---------------------------------------------------------------------------


def test_pull_input_methods_returns_callables():
    """Returns a dict of callable input methods."""
    result = EntityTester.pull_input_methods()
    assert isinstance(result, dict)
    assert len(result) > 0
    for name, fn in result.items():
        assert callable(fn), f"{name} is not callable"


def test_pull_input_methods_excludes():
    """Applies exclude filter."""
    result = EntityTester.pull_input_methods(exclude=["genetic"])
    assert not any("genetic" in name for name in result)


# ---------------------------------------------------------------------------
# EntityTestTask tests
# ---------------------------------------------------------------------------


def test_entity_test_task_creation():
    """EntityTestTask can be created with the new single-dict structure."""
    task = EntityTestTask(
        entity="Organization",
        method="create",
        arg_dict={"name": "gen_alphanumeric"},
    )
    assert task.entity == "Organization"
    assert task.method == "create"
    assert task.arg_dict == {"name": "gen_alphanumeric"}
    assert not hasattr(task, "field_dict")


def test_entity_test_task_mock_execute():
    """Mock execute returns the task as a dict."""
    task = EntityTestTask(
        entity="Organization",
        method="create",
        arg_dict={"name": "gen_alphanumeric"},
    )
    result = task.execute(mock=True)
    assert isinstance(result, dict)
    assert result["entity"] == "Organization"
    assert result["method"] == "create"
    assert "arg_dict" in result
