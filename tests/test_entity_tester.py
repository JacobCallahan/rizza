# -*- encoding: utf-8 -*-
"""Tests for rizza.entity_tester."""
import pytest
from rizza import entity_tester
from rizza.helpers import config


@pytest.fixture(scope="session", autouse=True)
def init_config():
    """Init the class, to provide the nailgun configuration."""
    conf = config.Config()


def test_positive_create_entitytester():
    """Create a new tester."""
    e_tester = entity_tester.EntityTester('Product')
    assert e_tester.entity == 'Product'
    e_tester.prep()
    assert 'create' in dir(e_tester.entity)
    assert 'repository' in e_tester.fields
    assert 'sync' in e_tester.methods


def test_negative_create_entitytester():
    """Attempt to create a new tester with bad name."""
    e_tester = entity_tester.EntityTester('Nothing')
    assert e_tester.entity == 'Nothing'
    with pytest.raises(Exception) as err_msg:
        e_tester.prep()
        assert err_msg == 'Entity Nothing not found.'
        assert not e_tester.fields
        assert not e_tester.methods


def test_positive_brute_generator():
    """Create a new tester and validate the brute force
    test generator.
    """
    e_tester = entity_tester.EntityTester('Product')
    e_tester.prep()
    brute_gen = e_tester.brute_force(max_fields=3, max_inputs=3)
    test = next(brute_gen)
    assert isinstance(test, entity_tester.EntityTestTask)
    assert test.entity == 'Product'
    assert test.method in e_tester.methods
    for field, inpt in test.field_dict.items():
        assert field in e_tester.fields
        assert inpt in e_tester.pull_input_methods()


def test_positive_create_maimap():
    """Create a Method Atrribute Input map and validate."""
    e_tester = entity_tester.EntityTester('Product')
    e_tester.prep()
    inpts = e_tester.pull_input_methods()
    fields = e_tester.pull_fields(e_tester.entity)
    maimap = entity_tester.MaIMap(fields=fields, inputs=inpts)
    assert maimap.x_labels == list(fields.keys())
    assert maimap.y_labels == list(inpts.keys())
    assert len(maimap.mai_map) == len(inpts)
    assert len(maimap.mai_map[0]) == len(fields)
    assert maimap.point(1, 1)['value'] is None
    maimap.point(1, 1, 'Pass')
    assert maimap.point(1, 1)['value'] == 'Pass'


def test_positive_search_maimap():
    """Create a Method Atrribute Input map, adjust values, and search."""
    e_tester = entity_tester.EntityTester('Product')
    e_tester.prep()
    inpts = e_tester.pull_input_methods()
    fields = e_tester.pull_fields(e_tester.entity)
    maimap = entity_tester.MaIMap(fields=fields, inputs=inpts)
    maimap.point(1, 1, 'Pass')
    maimap.point(1, 3, 'Pass')
    maimap.point(3, 2, 'Pass')
    results = maimap.find('Pass')
    assert results == [(1, 1), (1, 3), (3, 2)]
