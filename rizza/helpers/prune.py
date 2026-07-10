"""A utility that tries saved genetic tests and removes those failing"""
import asyncio
import json
import logging

import yaml

logger = logging.getLogger(__name__)

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


def count_pending_tests(conf, entity="_all", method="_all"):
    """Count how many positive tests would be validated.

    :param conf: Config instance.
    :param entity: Entity name or "_all".
    :param method: Method name or "_all".
    :returns: Integer count of matching saved positive tests.
    """
    if entity == "_all":
        return sum(
            count_pending_tests(conf, e, method)
            for e in entity_tester.EntityTester.pull_entities()
        )
    test_file = conf.base_dir / "data" / "genetic_tests" / f"{entity}.yaml"
    if not test_file.exists() or test_file.stat().st_size < MIN_FILE_SIZE:
        return 0
    tests = yaml.safe_load(test_file.read_text()) or {}
    return sum(
        1
        for k in tests
        if len(k.split(" ")) == 3
        and k.split(" ")[2] == "positive"
        and method in {"_all", k.split(" ")[1]}
    )


def validate_tests(conf, entity="_all", method="_all", prune=False):
    """Validate saved genetic tests; optionally prune failures.

    :param conf: Config instance.
    :param entity: Entity name, or "_all" for all entities.
    :param method: Method name, or "_all" for all saved methods.
    :param prune: If True, remove failing tests from the YAML.
    :returns: List of validation result dicts from GeneticEntityTester.run_validation().
    """
    if entity == "_all":
        all_results = []
        for target in list(entity_tester.EntityTester.pull_entities()):
            all_results.extend(validate_tests(conf, target, method, prune))
        return all_results

    test_file = conf.base_dir / "data" / "genetic_tests" / f"{entity}.yaml"
    if not test_file.exists() or test_file.stat().st_size < MIN_FILE_SIZE:
        return []

    tests = yaml.safe_load(test_file.read_text()) or {}
    to_remove = []
    results = []

    for test_name in list(tests.keys()):
        parts = test_name.split(" ")
        if len(parts) != 3 or parts[2] != "positive":
            continue
        meth = parts[1]
        if method not in {"_all", meth}:
            continue

        validation = genetic_tester.GeneticEntityTester(conf, entity, meth).run_validation()
        if validation is None:
            continue
        results.append(validation)

        # Thread-safe progress advance (Rich Progress uses an internal lock)
        _progress = getattr(conf, "_progress", None)
        _task = getattr(conf, "_validate_task", None)
        if _progress is not None and _task is not None:
            _progress.advance(_task)

        if not validation["passed"] and prune:
            to_remove.append(test_name)

    if to_remove:
        for name in to_remove:
            del tests[name]
        test_file.unlink()
        if tests:
            yaml.dump(tests, test_file.open("w+"), default_flow_style=False)
        logger.info(f"Pruned {len(to_remove)} test(s) from {entity}")

    if test_file.exists() and test_file.stat().st_size < MIN_FILE_SIZE:
        test_file.unlink()

    return results


async def _async_validate(conf, entity, method, prune, sem):
    """Run a single entity's validation in the default executor."""
    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, validate_tests, conf, entity, method, prune)


async def _async_validate_all(conf, method, prune, sem):
    """Run validation for all entities concurrently."""
    tasks = [
        asyncio.ensure_future(_async_validate(conf, entity, method, prune, sem))
        for entity in list(entity_tester.EntityTester.pull_entities())
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Validation task error: {r}")
        elif r:
            all_results.extend(r)
    return all_results


def _save_failed(results, base_dir):
    failed = {}
    for r in results:
        if not r.get("passed"):
            failed.setdefault(r["entity"], []).append(r["method"])
    out = base_dir / "validation" / "last_failed.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(failed, indent=2))


def async_validate_tests(conf, entity="_all", method="_all", prune=False, async_limit=100):
    """Asynchronously validate saved genetic tests.

    :param conf: Config instance.
    :param entity: Entity name or "_all".
    :param method: Method name or "_all".
    :param prune: Remove failing tests if True.
    :param async_limit: Maximum concurrent validations.
    :returns: List of validation result dicts.
    """
    if entity != "_all":
        results = validate_tests(conf, entity, method, prune)
        _save_failed(results, conf.base_dir)
        return results

    sem = asyncio.Semaphore(async_limit)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(_async_validate_all(conf, method, prune, sem))
        _save_failed(results, conf.base_dir)
        return results
    finally:
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()
        asyncio.set_event_loop(None)
