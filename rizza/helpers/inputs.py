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
    print('\n\nCreating a(n) {}...'.format(entity))
    return GeneticEntityTester(config, entity, 'create').run_best()


def genetic_unknown(config, entity='Organization', max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester
    if not config.RIZZA['GENETICS']['ALLOW RECURSION']:
        return None
    if not max_generations:
        max_generations = config.RIZZA['GENETICS']['MAX RECURSIVE GENERATIONS']
    print('\n\nAttempting to create a(n) {}...'.format(entity))
    gtester = GeneticEntityTester(
        config, entity, 'create', max_generations=max_generations)
    if not gtester._load_test():
        gtester.run()
    print('Resuming parent task.\n\n')
    return gtester.run_best()
