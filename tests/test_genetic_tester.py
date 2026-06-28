"""Tests for rizza.genetic_tester."""
from pathlib import Path
import tempfile

import pytest

from rizza import genetic_tester
from rizza.helpers import config

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
