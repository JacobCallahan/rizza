from fauxfactory import *  # noqa: F403


def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()  # noqa: F405


def gen_small_integer():
    """Return a small positive integer suitable for pagination (per_page, page, limit, etc.)."""
    from random import randint

    return randint(1, 100)


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


__creating = __import__("contextvars").ContextVar("_creating", default=frozenset())
__known_depth = __import__("contextvars").ContextVar("_known_depth", default=0)
__active_creates_lock = __import__("threading").Lock()
__active_creates: set[str] = set()


def get_entity_id(config, entity="Organization"):
    """Return the id of a previously created entity for use as a method dependency.

    Like genetic_known but does NOT count against max_recursive_depth — intended
    for the entity_tester catch block where an entity method requires the entity's
    own id.  Cycle detection (via __creating) is still enforced.
    """
    import logging

    from rizza.genetic_tester import GeneticEntityTester

    if not config.rizza.genetics.allow_dependencies:
        return None

    currently_creating = __creating.get()
    if entity in currently_creating:
        logging.getLogger(__name__).debug(
            f"Cycle detected: already creating {entity}; skipping id lookup."
        )
        return None

    cycle_token = __creating.set(currently_creating | {entity})
    try:
        gtester = GeneticEntityTester(config, entity, "create")
        return gtester.run_best()
    finally:
        __creating.reset(cycle_token)


def genetic_known(config, entity="Organization"):
    """Return the id of a previously created entity, or None if no saved test exists.

    Does not trigger a new genetic search — callers must run `rizza genetic -e Entity -m create`
    first to save a passing organism.
    """
    import logging

    from rizza.genetic_tester import GeneticEntityTester

    if not config.rizza.genetics.allow_dependencies:
        return None

    currently_creating = __creating.get()
    if entity in currently_creating:
        logging.getLogger(__name__).debug(
            f"Cycle detected: already creating {entity}; skipping known lookup."
        )
        return None

    depth = __known_depth.get() + 1
    if depth >= config.rizza.genetics.max_recursive_depth:
        return None

    depth_token = __known_depth.set(depth)
    cycle_token = __creating.set(currently_creating | {entity})
    try:
        gtester = GeneticEntityTester(config, entity, "create")
        return gtester.run_best()
    finally:
        __creating.reset(cycle_token)
        __known_depth.reset(depth_token)


def genetic_index(config, entity="Organization"):
    """Return an ID of an existing entity by listing via _list_from_index().

    Useful for built-in/pre-existing entities (AuthSource, Organization, Location)
    that ship with the product and don't need to be created.
    """
    import logging

    from rizza.entity_tester import EntityTester

    try:
        entity_cls = EntityTester.pull_entities().get(entity)
        if not entity_cls:
            return -1
        inst = entity_cls()
        results = inst._list_from_index()
        if isinstance(results, list) and results:
            return results[0].id
    except Exception as err:
        logging.getLogger(__name__).debug(f"genetic_index({entity}) failed: {err}")
    return -1


__recursion_lock = __import__("threading").Lock()


def genetic_unknown(config, entity="Organization", max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    import logging

    from rizza.genetic_tester import GeneticEntityTester

    __logger = logging.getLogger(__name__)

    if not config.rizza.genetics.allow_recursion or not config.rizza.genetics.allow_dependencies:
        return None

    currently_creating = __creating.get()
    if entity in currently_creating:
        __logger.debug(
            f"Cycle detected: already creating {entity}; skipping recursive exploration."
        )
        return None

    # In replay mode (run_best/run_validation), just replay — no concurrency guard needed.
    from rizza.genetic_tester import _replay_mode

    if _replay_mode.get():
        cycle_token = __creating.set(currently_creating | {entity})
        try:
            gtester = GeneticEntityTester(config, entity, "create")
            return gtester.run_best()
        finally:
            __creating.reset(cycle_token)

    if not max_generations:
        max_generations = config.rizza.genetics.max_recursive_generations

    with __recursion_lock:
        depth = getattr(config.rizza.genetics, "recursion_depth", 0) + 1
        config.rizza.genetics.recursion_depth = depth

    if depth >= config.rizza.genetics.max_recursive_depth:
        __logger.warning("Reached max recursion depth.")
        with __recursion_lock:
            config.rizza.genetics.recursion_depth -= 1
        return None

    cycle_token = __creating.set(currently_creating | {entity})
    __logger.info(f"Attempting to create {entity}...")
    gtester = GeneticEntityTester(config, entity, "create", max_generations=max_generations)
    try:
        if not gtester._load_test():
            with __active_creates_lock:
                already_searching = entity in __active_creates
                if not already_searching:
                    __active_creates.add(entity)
            if already_searching:
                __logger.debug(
                    f"Another thread is already searching for {entity}; "
                    "will try run_best() with whatever is saved."
                )
            else:
                try:
                    gtester.run(save_only_passed=True)
                finally:
                    with __active_creates_lock:
                        __active_creates.discard(entity)
        __logger.info("Resuming parent task.")
        return gtester.run_best()
    finally:
        __creating.reset(cycle_token)
        with __recursion_lock:
            config.rizza.genetics.recursion_depth -= 1
