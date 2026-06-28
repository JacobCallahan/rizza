from fauxfactory import *  # noqa: F403


def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()  # noqa: F405


def gen_choice():
    """Overriden since it doesn't apply."""
    return


def gen_list():
    """Overridden since fauxfactory's version requires item_schema."""
    return []


def gen_dict():
    """Overridden since fauxfactory's version requires a schema."""
    return {}


def gen_json():
    """Overridden since fauxfactory's version requires a schema."""
    return "{}"


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
    """Return the id of a previously created entity, or None if no saved test exists.

    Does not trigger a new genetic search — callers must run `rizza genetic -e Entity -m create`
    first to save a passing organism.
    """
    from rizza.genetic_tester import GeneticEntityTester

    if not config.rizza.genetics.allow_dependencies:
        return None

    depth = getattr(config.rizza.genetics, "known_depth", 0) + 1
    config.rizza.genetics.known_depth = depth
    if depth >= config.rizza.genetics.max_recursive_depth:
        config.rizza.genetics.known_depth -= 1
        return None

    try:
        gtester = GeneticEntityTester(config, entity, "create")
        return gtester.run_best()
    finally:
        config.rizza.genetics.known_depth -= 1


def genetic_unknown(config, entity="Organization", max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    import logging

    from rizza.genetic_tester import GeneticEntityTester

    __logger = logging.getLogger(__name__)

    if not config.rizza.genetics.allow_recursion or not config.rizza.genetics.allow_dependencies:
        return None

    if not max_generations:
        max_generations = config.rizza.genetics.max_recursive_generations

    config.rizza.genetics.recursion_depth = (
        getattr(config.rizza.genetics, "recursion_depth", 0) + 1
    )
    if config.rizza.genetics.recursion_depth >= config.rizza.genetics.max_recursive_depth:
        __logger.warning("Reached max recursion depth.")
        config.rizza.genetics.recursion_depth -= 1
        return 1

    __logger.info(f"Attempting to create {entity}...")
    gtester = GeneticEntityTester(config, entity, "create", max_generations=max_generations)
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    __logger.info("Resuming parent task.")
    config.rizza.genetics.recursion_depth -= 1
    return gtester.run_best()
