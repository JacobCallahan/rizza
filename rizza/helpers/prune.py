"""A utility that tries saved genetic tests and removes those failing"""
import asyncio

from logzero import logger
import yaml

from rizza import entity_tester, genetic_tester

MIN_FILE_SIZE = 10


def genetic_prune(conf, entity="All"):
    """Check all saved genetic_tester tests for an entity, prune failures"""
    if entity == "All":
        for target in list(entity_tester.EntityTester.pull_entities()):
            genetic_prune(conf, target)
    else:
        test_file = conf.base_dir.joinpath(f"data/genetic_tests/{entity}.yaml")
        logger.debug(f"Current target file: {test_file}")
        to_remove = []
        if test_file.exists() and test_file.stat().st_size > MIN_FILE_SIZE:
            logger.debug(f"Beginning tests for {entity}")
            tests = yaml.load(test_file.open("r"), Loader=yaml.FullLoader)
            for test in tests:
                ent, method, mode = test.split(" ")
                if mode == "positive":
                    logger.debug(f"Running test {method}")
                    result = genetic_tester.GeneticEntityTester(conf, entity, method).run_best()
                    if result == -1:
                        logger.debug(f"{test} failed.")
                        to_remove.append(test)
                    else:
                        logger.debug(f"{test} passed.")
            for test in to_remove:
                logger.warning(f"Removing {test} from {test_file}")
                del tests[test]
            logger.debug(f"Deleting file {test_file}")
            test_file.unlink()
            logger.debug(f"Writing tests to {test_file}")
            yaml.dump(tests, test_file.open("w+"), default_flow_style=False)
            logger.info(f"Done pruning {entity}")
        if test_file.exists() and test_file.stat().st_size < MIN_FILE_SIZE:
            logger.warning(f"Deleting empty file {test_file}")
            test_file.unlink()


async def _async_prune(conf, entity, loop, sem):
    """Run an individual prune task"""
    async with sem:
        await loop.run_in_executor(
            None,  # use default executor
            genetic_prune,
            conf,
            entity,  # function and args
        )


async def _async_prune_all(conf, loop, sem):
    """Construct all the prune tasks, and await them"""
    tasks = [
        asyncio.ensure_future(_async_prune(conf, entity, loop, sem))
        for entity in list(entity_tester.EntityTester.pull_entities())
    ]
    await asyncio.wait(tasks)


def async_genetic_prune(conf, entity="All", async_limit=100):
    """Asynchronously perform a genetic prune for all entities"""
    if entity != "All":
        genetic_prune(conf, entity)
        return

    sem = asyncio.Semaphore(async_limit)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_prune_all(conf, loop, sem))
    loop.close()
