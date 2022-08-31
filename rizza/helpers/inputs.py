from fauxfactory import *
import random

def gen_string():
    """Overriden since it doesn't apply."""
    return gen_alphanumeric()


def gen_choice():
    """Overriden since it doesn't apply."""
    return None


def content_type(choice=1):
    choices = {
        1: 'yum',
        2: 'puppet',
        3: 'docker',
        4: 'file'
    }
    return choices.get(choice, choices[1])


def yum_url(choice=1):
    choices = {
        1: 'https://omaciel.fedorapeople.org/fakerepo01/',
        2: 'https://omaciel.fedorapeople.org/fakerepo02/'
    }
    return choices.get(choice, choices[1])


def puppet_url(choice=1):
    choices = {
        1: 'https://omaciel.fedorapeople.org/7c74c2b8/',
        2: 'https://omaciel.fedorapeople.org/'
    }
    return choices.get(choice, choices[1])

def additional_nailgun_fields_setup(fields, types):
    """Configurate Nailgun field post creation to match more complex fields.
    if the nailgun field is:
        list -- choose a nailgun field, choose random type and fill the list
        dict -- is the same but use unique string as a key and random field as the value
        float -- create a float value as we do in nailgun
    recursively check whether there is not a new list or dict
    """
    new_fields = []
    for field in fields.values() if isinstance(fields, dict) else fields:
        if field == 'float':
            new_fields.append(random.random() * 10000)
        elif field == 'list':
            choices = [random.choice(types)] * random.randint(0, 2)
            new_field = additional_nailgun_fields_setup(choices, types)
            new_fields.append(new_field)
        elif field == 'dict':
            # TODO string has to be unique once it's created
            choices = {'gen_string': random.choice(types)}
            new_field = additional_nailgun_fields_setup(choices, types)
            new_fields.append(new_field)
        else:
            new_fields.append(field)
    return new_fields


def genetic_known(config, entity='Organization'):
    """Attempt to create a known entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester
    if not config.RIZZA['GENETICS']['ALLOW DEPENDENCIES']:
        return None
    gtester = GeneticEntityTester(config, entity, 'create')
    if not gtester._load_test():
        gtester.run(save_only_passed=True)
    return gtester.run_best()


def genetic_unknown(config, entity='Organization', max_generations=None):
    """Attempt to create an unknown entity and return the id"""
    from rizza.genetic_tester import GeneticEntityTester
    from logzero import logger
    if (not config.RIZZA['GENETICS']['ALLOW RECURSION'] or
        not config.RIZZA['GENETICS']['ALLOW DEPENDENCIES']):
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
