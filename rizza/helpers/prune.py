# -*- encoding: utf-8 -*-
"""A utility that tries saved genetic tests and removes those failing"""
import asyncio
import yaml
from pathlib import Path
from logzero import logger
from rizza import entity_tester
from rizza import genetic_tester


def genetic_prune(conf, entity='All'):
    """Check all saved genetic_tester tests for an entity, prune failures"""
    if entity == 'All':
        for target in list(entity_tester.EntityTester.pull_entities()):
            genetic_prune(conf, target)
    else:
        test_file = conf.base_dir.joinpath(
            'data/genetic_tests/{}.yaml'.format(entity))
        logger.debug('Current target file: {}'.format(test_file))
        to_remove = []
        if test_file.exists() and test_file.stat().st_size > 10:
            logger.debug('Beginning tests for {}'.format(entity))
            tests = yaml.load(test_file.open('r'), Loader=yaml.FullLoader)
            for test in tests:
                ent, method, mode = test.split(' ')
                if mode == 'positive':
                    logger.debug('Running test {}'.format(method))
                    result = genetic_tester.GeneticEntityTester(
                        conf, entity, method
                    ).run_best()
                    if result == -1:
                        logger.debug('{} failed.'.format(test))
                        to_remove.append(test)
                    else:
                        logger.debug('{} passed.'.format(test))
            for test in to_remove:
                logger.warning('Removing {} from {}'.format(test, test_file))
                del tests[test]
            logger.debug('Deleting file {}'.format(test_file))
            test_file.unlink()
            logger.debug('Writing tests to {}'.format(test_file))
            yaml.dump(tests, test_file.open('w+'), default_flow_style=False)
            logger.info('Done pruning {}'.format(entity))
        if test_file.exists() and test_file.stat().st_size < 10:
            logger.warning('Deleting empty file {}'.format(test_file))
            test_file.unlink()


async def _async_prune(conf, entity, loop, sem):
    """Run an individual prune task"""
    async with sem:
        await loop.run_in_executor(
            None,  # use default executor
            genetic_prune, conf, entity  # function and args
        )


async def _async_prune_all(conf, loop, sem):
    """Construct all the prune tasks, and await them"""
    tasks = [
        asyncio.ensure_future(_async_prune(conf, entity, loop, sem))
        for entity in list(entity_tester.EntityTester.pull_entities())
    ]
    await asyncio.wait(tasks)


def async_genetic_prune(conf, entity='All', async_limit=100):
    """Asynchronously perform a genetic prune for all entities"""
    if entity != 'All':
        genetic_prune(conf, entity)
        return

    sem = asyncio.Semaphore(async_limit)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_prune_all(conf, loop, sem))
    loop.close()
