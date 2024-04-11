from fauxfactory import *  # noqa: F403


def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()  # noqa: F405


def gen_choice():
    """Overriden since it doesn't apply."""
    return


def content_type(choice=1):
    choices = {1: "yum", 2: "puppet", 3: "docker", 4: "file"}
    return choices.get(choice, choices[1])


def yum_url(choice=1):
    choices = {
        1: "https://omaciel.fedorapeople.org/fakerepo01/",
        2: "https://omaciel.fedorapeople.org/fakerepo02/",
    }
    return choices.get(choice, choices[1])


def puppet_url(choice=1):
    choices = {
        1: "https://omaciel.fedorapeople.org/7c74c2b8/",
        2: "https://omaciel.fedorapeople.org/",
    }
    return choices.get(choice, choices[1])


def genetic_known(config, entity="Organization"):
    """Attempt to create a known entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester

    if not config.RIZZA["GENETICS"]["ALLOW DEPENDENCIES"]:
        return None
    gtester = GeneticEntityTester(config, entity, "create")
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    return gtester.run_best()


def genetic_unknown(config, entity="Organization", max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    from logzero import logger

    from rizza.genetic_tester import GeneticEntityTester

    if (
        not config.RIZZA["GENETICS"]["ALLOW RECURSION"]
        or not config.RIZZA["GENETICS"]["ALLOW DEPENDENCIES"]
    ):
        return None

    if not max_generations:
        max_generations = config.RIZZA["GENETICS"]["MAX RECURSIVE GENERATIONS"]

    config.RIZZA["GENETICS"]["recursion depth"] = config.RIZZA["GENETICS"].get(
        "recursion depth", 0
    )
    if (
        config.RIZZA["GENETICS"]["recursion depth"]
        >= config.RIZZA["GENETICS"]["MAX RECURSIVE DEPTH"]
    ):
        logger.warning("Reached max recursion depth.")
        config.RIZZA["GENETICS"]["recursion depth"] -= 1
        return 1

    logger.info(f"Attempting to create {entity}...")
    gtester = GeneticEntityTester(config, entity, "create", max_generations=max_generations)
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    logger.info("Resuming parent task.")
    config.RIZZA["GENETICS"]["recursion depth"] -= 1
    return gtester.run_best()
