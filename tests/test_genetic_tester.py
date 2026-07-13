"""Tests for rizza.genetic_tester."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from rizza import genetic_tester
from rizza.helpers import config
from rizza.helpers.telemetry import PermutationStore

_EXAMPLE_DIR = Path(__file__).parent.parent / "config"
RECURSE_LIMIT = 1337


@pytest.fixture(scope="module")
def conf():
    with tempfile.TemporaryDirectory() as tmpdir:
        for ex in _EXAMPLE_DIR.glob("*.pconf.example"):
            (Path(tmpdir) / ex.name.removesuffix(".example")).write_text(ex.read_text())
        yield config.Config(cfg_dir=tmpdir)


def test_positive_create(conf):
    """Init the class and check the defaults match the config"""
    gen_test = genetic_tester.GeneticEntityTester(conf, "Organization", "create")
    assert gen_test.config
    assert gen_test.entity == "Organization"
    assert gen_test.method == "create"
    assert not gen_test.fresh
    assert not gen_test.seek_bad
    assert gen_test.max_generations == gen_test.config.rizza.genetics.max_generations
    assert gen_test.population_count == gen_test.config.rizza.genetics.population_count
    assert gen_test.test_name == "Organization create positive"


def test_positive_config_overrides(conf):
    """Check that the post init overrides config values"""
    gen_test = genetic_tester.GeneticEntityTester(
        conf,
        "Organization",
        "create",
        max_recursive_generations=RECURSE_LIMIT,
        disable_recursion=True,
        max_recursive_depth=RECURSE_LIMIT,
    )
    assert gen_test.config.rizza.genetics.max_recursive_generations == RECURSE_LIMIT
    assert not gen_test.config.rizza.genetics.allow_recursion
    assert gen_test.config.rizza.genetics.max_recursive_depth == RECURSE_LIMIT


def test_positive_mock_run(conf):
    """Run a mock series of genetic algorithm-based tests"""
    gen_test = genetic_tester.GeneticEntityTester(
        conf, "Organization", "create", max_generations=10
    )
    gen_test.run(mock=True)


def test_positive_judge(conf):
    """Make sure that the judge function returns a correct result"""
    gen_test = genetic_tester.GeneticEntityTester(conf, "Organization", "create")
    for criteria, points in conf.rizza.genetics.criteria.items():
        assert gen_test._judge(result=criteria) == points


def test_positive_mock_judge(conf):
    """Make sure that the mock judge function return an integer"""
    gen_test = genetic_tester.GeneticEntityTester(conf, "Organization", "create")
    assert isinstance(gen_test._judge(mock=True), int)


def test_run_validation_records_telemetry(conf, tmp_path):
    """run_validation() should record its pass/fail outcome to the telemetry store."""
    gen_test = genetic_tester.GeneticEntityTester(conf, "Organization", "validate_telemetry")
    fake_genes = [["name"], ["gen_email"]]
    db_path = tmp_path / "permutations.db"
    isolated_store = PermutationStore(db_path=db_path)
    with (
        patch.object(gen_test, "_load_test", return_value=fake_genes),
        patch(
            "rizza.entity_tester.EntityTestTask.execute",
            return_value={"result": {"pass": {"id": 1}}, "resolved_args": {"name": "foo"}},
        ),
        patch(
            "rizza.genetic_tester.PermutationStore.from_config",
            return_value=isolated_store,
        ),
    ):
        validation = gen_test.run_validation()

    assert validation["passed"] is True

    store = PermutationStore(db_path=db_path)
    try:
        rows = store.query_method_summary("Organization")
        row = next(r for r in rows if r["name"] == "Organization.validate_telemetry")
        assert row["total_permutations"] == 1
        assert row["total_passes"] == 1
        assert row["total_fails"] == 0
    finally:
        store.close()


def _make_fake_entity(has_annotation=False):
    """Build a fake entity class with an organization_id param."""
    if has_annotation:

        def fake_init(self, name, organization_id: int | None = None):
            pass

    else:

        def fake_init(self, name, organization_id=None):
            pass

    cls = type("FakeEntity", (), {"__init__": fake_init})

    def create(self, name=None, organization_id=None):
        pass

    cls.create = create
    return cls


def test_build_type_pools_unannotated_fk_params(conf):
    """_build_type_pools should detect FK params by name even without annotations."""
    FakeEntity = _make_fake_entity(has_annotation=False)

    with patch("rizza.entity_tester.EntityTester.pull_entities") as mock_pull:
        mock_pull.return_value = {"Organization": MagicMock(), "FakeEntity": FakeEntity}
        gen_test = genetic_tester.GeneticEntityTester(conf, "FakeEntity", "create")

    assert "organization_id" in gen_test._type_pools
    pool = gen_test._type_pools["organization_id"]
    assert all("genetic" in g for g in pool)
    assert len(pool) > 0
