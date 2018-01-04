# -*- encoding: utf-8 -*-
"""Tests for rizza.genetic_tester."""
import pytest
from rizza import genetic_tester
from rizza.helpers import config

CONF = config.Config()

def test_positive_create():
    """Init the class and check the defaults match the config"""
    gen_test = genetic_tester.GeneticEntityTester(
        CONF, 'Organization', 'create'
    )
    assert gen_test.config
    assert gen_test.entity == 'Organization'
    assert gen_test.method == 'create'
    assert not gen_test.fresh
    assert not gen_test.seek_bad
    assert gen_test.max_generations == gen_test.config.RIZZA[
        'GENETICS']['MAX GENERATIONS']
    assert gen_test.population_count == gen_test.config.RIZZA[
        'GENETICS']['POPULATION COUNT']
    assert gen_test.test_name == 'Organization create positive'

def test_positive_config_overrides():
    """Check that the post init overrides config values"""
    gen_test = genetic_tester.GeneticEntityTester(
        CONF, 'Organization', 'create',
        max_recursive_generations=1337,
        disable_recursion=True,
        max_recursive_depth=1337
    )
    assert gen_test.config.RIZZA['GENETICS'][
        'MAX RECURSIVE GENERATIONS'] == 1337
    assert not gen_test.config.RIZZA['GENETICS']['ALLOW RECURSION']
    assert gen_test.config.RIZZA['GENETICS']['MAX RECURSIVE DEPTH'] == 1337

def test_positive_mock_run():
    """Run a mock series of genetic algorithm-based tests"""
    gen_test = genetic_tester.GeneticEntityTester(
        CONF, 'Organization', 'create', max_generations=10)
    gen_test.run(mock=True)

def test_positive_judge():
    """Make sure that the judge function returns a correct result"""
    gen_test = genetic_tester.GeneticEntityTester(
        CONF, 'Organization', 'create'
    )
    for criteria, points in CONF.RIZZA['GENETICS']['CRITERIA'].items():
        assert gen_test._judge(result=criteria) == points

def test_positive_mock_judge():
    """Make sure that the mock judge function return an integer"""
    gen_test = genetic_tester.GeneticEntityTester(
        CONF, 'Organization', 'create'
    )
    assert isinstance(gen_test._judge(mock=True), int)
