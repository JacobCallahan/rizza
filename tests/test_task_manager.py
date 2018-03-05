# -*- encoding: utf-8 -*-
"""Tests for rizza.task_manager."""
import os
import json
import pytest
from rizza import task_manager
from rizza.helpers import logger

IMPORT_FILE = 'tests/data/example.txt'
EXPORT_FILE = 'tests/data/temp_export.txt'
LOG_FILE = 'logs/temp.log'


def test_positive_import_tasks():
    """Import tasks from a pre-created file and validate contents."""
    tasks = task_manager.TaskManager.import_tasks(IMPORT_FILE)
    task = next(tasks)
    assert task.__class__.__name__ == 'EntityTestTask'
    assert isinstance(task.entity, str)
    assert isinstance(task.method, str)
    assert isinstance(task.field_dict, dict)
    assert isinstance(task.arg_dict, dict)


def test_positive_export_tasks():
    """Import pre-created tasks, export, then ensure they match."""
    tasks = task_manager.TaskManager.import_tasks(IMPORT_FILE)
    task_manager.TaskManager.export_tasks(EXPORT_FILE, tasks)
    # re-import base tasks since generator was exhausted
    tasks = task_manager.TaskManager.import_tasks(IMPORT_FILE)
    exported = task_manager.TaskManager.import_tasks(EXPORT_FILE)
    assert list(tasks) == list(exported)
    os.remove(EXPORT_FILE)


def test_positive_run_tests():
    """Run mock tests and validate the generated results."""
    tasks = task_manager.TaskManager.import_tasks(IMPORT_FILE)
    logger.setup_logzero(LOG_FILE, 'info')
    task_manager.TaskManager.run_tests(tasks, True)
    with open(LOG_FILE) as test_file:
        for test in test_file:
            split_test = test.split('~')
            # The test data just before being ran must match 'after'
            if len(split_test) == 3:
                assert json.loads(split_test[1]) == json.loads(split_test[2])
    os.remove(LOG_FILE)
