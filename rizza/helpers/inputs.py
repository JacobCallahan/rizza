from fauxfactory import *


def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()


def gen_choice():
    """Overriden since it doesn't apply."""
    return None


def gen_alpha_long():
    return gen_alpha(256)


def gen_alphanumeric_long():
    return gen_alphanumeric(256)


def gen_cjk_long():
    return gen_cjk(256)


def gen_cyrillic_long():
    return gen_cyrillic(256)


def gen_html_long():
    return gen_html(256)


def gen_iplum_long():
    return gen_iplum(256)


def gen_latin1_long():
    return gen_latin1(256)


def gen_numeric_string_long():
    return gen_numeric_string(256)


def gen_utf8_long():
    return gen_utf8(256)


def genetic_known(config, entity='Organization'):
    """Attempt to create a known entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester
    gtester = GeneticEntityTester(config, entity, 'create')
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    return gtester.run_best()


def genetic_unknown(config, entity='Organization', max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester
    from logzero import logger
    if not config.RIZZA['GENETICS']['ALLOW RECURSION']:
        return None

    if not max_generations:
        max_generations = config.RIZZA['GENETICS']['MAX RECURSIVE GENERATIONS']

    config.RIZZA['GENETICS']['recursion depth'] = config.RIZZA[
        'GENETICS'].get('recursion depth', 0)
    if config.RIZZA['GENETICS']['recursion depth'] >= config.RIZZA[
        'GENETICS']['MAX RECURSIVE DEPTH']:
        logger.warning('Reached max recursion depth.')
        config.RIZZA['GENETICS']['recursion depth'] -= 1
        return 1

    logger.info('Attempting to create {}...'.format(entity))
    gtester = GeneticEntityTester(
        config, entity, 'create', max_generations=max_generations)
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    logger.info('Resuming parent task.')
    config.RIZZA['GENETICS']['recursion depth'] -= 1
    return gtester.run_best()
