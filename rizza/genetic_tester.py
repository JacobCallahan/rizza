# -*- encoding: utf-8 -*-
"""A module that provides utilities to test entities via genetic algorithms"""
import asyncio
import random
import yaml
import attr
from logzero import logger
from rizza import entity_tester
from rizza.helpers import genetics
from rizza.helpers.misc import dict_search


def run_all_entities(**kwargs):
    """Iterate through all known entities and attempt to """
    debug = kwargs.pop('debug')
    async_mode = kwargs.pop('async_mode')
    if not async_mode:
        del kwargs['max_running']

    for entity in list(entity_tester.EntityTester.pull_entities()):
        kwargs['entity'] = entity
        try:
            if async_mode:
                gtester = AsyncGeneticEntityTester(**kwargs)
            else:
                gtester = GeneticEntityTester(**kwargs)
        except:
            continue
        kwargs['config'].init_logger(
            path=kwargs['config'].base_dir.joinpath(
                'logs/genetic/{}.log'.format(gtester.test_name)),
            level='debug' if debug else None
        )
        logger.info(f'Starting tests for {entity}')
        gtester.run()
    logger.info('Finished testing all entities!')

@attr.s()
class GeneticEntityTester():
    """Class that handles all aspects of genetic algorithm-based testing

    :param config: Required. A config class instance.
    :param entity: A string name of the target entity.
    :param method: A string name of the entity's target method.
    :param population_count: Integer specifying the number in each generation.
    :param max_generations: Integer specifying the max number of generations.
    :param seek_bad: Boolean noting whether to favor bad results.
    :param fresh: Boolean noting whether to use the last best saved result.

    """

    config = attr.ib()
    entity = attr.ib(validator=attr.validators.instance_of(str))
    method = attr.ib(validator=attr.validators.instance_of(str))
    population_count = attr.ib(default=None)
    max_generations = attr.ib(default=None)
    max_recursive_generations = attr.ib(default=None)
    max_recursive_depth = attr.ib(default=None)
    disable_dependencies = attr.ib(default=None)
    disable_recursion = attr.ib(default=None)
    seek_bad = attr.ib(default=False)
    fresh = attr.ib(default=False)

    def __attrs_post_init__(self):
        """Perform more complex class initialzation"""
        # Entity method positive/negative
        self.test_name = '{} {} {}'.format(
            self.entity, self.method,
            'negative' if self.seek_bad else 'positive'
        )
        # If for some reason, the genetic config wasn't populated
        if not self.config.RIZZA.get('GENETICS', None):
            # try to load it again
            self.config._load_genetics()
        if not self.population_count:
            self.population_count = (
                self.config.RIZZA['GENETICS']['POPULATION COUNT'])
        if not self.max_generations:
            self.max_generations = (
                self.config.RIZZA['GENETICS']['MAX GENERATIONS'])

        # cli overrides
        if self.max_recursive_generations:
            self.config.RIZZA['GENETICS'][
                'MAX RECURSIVE GENERATIONS'] = self.max_recursive_generations
        if self.disable_dependencies:
            self.config.RIZZA['GENETICS']['ALLOW DEPENDENCIES'] = False
        if self.disable_recursion:
            self.config.RIZZA['GENETICS']['ALLOW RECURSION'] = False
        if self.max_recursive_depth:
            self.config.RIZZA['GENETICS'][
                'MAX RECURSIVE DEPTH'] = self.max_recursive_depth

        self._entity_inst = entity_tester.EntityTester.pull_entities()[self.entity]
        meths = entity_tester.EntityTester.pull_methods(self._entity_inst)
        if meths:
            self._method_inst = meths.get(self.method, None)
        else:
            self._method_inst = None
        self._etester = entity_tester.EntityTester(self.entity)
        self._etester.prep()

    def _save_organism(self, test):
        """Save the test organism to the appropriate file in data/genetic_tests"""
        test_file = self.config.base_dir.joinpath(
            'data/genetic_tests/{}.yaml'.format(self.entity))
        test_file.parent.mkdir(parents=True, exist_ok=True)
        tests = yaml.load(test_file.open('r+'), Loader=yaml.FullLoader) or {}
        tests[self.test_name] = attr.asdict(
            self._genes_to_task(test.genes),
            filter=lambda attr, value: attr.name != 'config')
        yaml.dump(tests, test_file.open('w+'), default_flow_style=False)

    def _load_test(self):
        """Load in the last test stored in data/genetic_tests, if any exist"""
        test_file = self.config.base_dir.joinpath(
            'data/genetic_tests/{}.yaml'.format(self.entity))
        test_file.parent.mkdir(parents=True, exist_ok=True)
        if test_file.exists():
            tests = yaml.load(test_file.open('r'), Loader=yaml.FullLoader) or {}
            best = tests.get(self.test_name, False)
            if best:
                # convert the yaml format to a gene list
                fields, field_inputs = ([], [])
                for field, inpt in best['field_dict'].items():
                    fields.append(field)
                    field_inputs.append(inpt)
                args, arg_inputs = ([], [])
                for arg, inpt in best['arg_dict'].items():
                    args.append(arg)
                    arg_inputs.append(inpt)
                return [fields, field_inputs, args, arg_inputs]
        else:
            test_file.touch()
        return False

    def _judge(self, result=None, mock=False):
        """Return a numeric value for the given result"""
        if mock:  # Used for testing the class without true execution
            return random.randint(-1000, 1000)
        total = -1

        # todo yake - keyword extraction with probabilities to all words, the lower the probability the more important word,
        # match whether some word in error message is one of the fields if give it higher probability so it would be probably chosen

        for criteria, points in self.config.RIZZA['GENETICS']['CRITERIA'].items():
            if dict_search(criteria, result):
                total += points
                if total == -1:
                    total += 1
        if total == -1:
            logger.warning(f'Result was not found between criteria, therefore not judged {result},'
                           'please add criteria to config.py')
        return total

    def _genes_to_task(self, genes):
        """Turn a gene list into an Entity Test Task"""
        field_dict = {field: inpt for (field, inpt) in zip(genes[0], genes[1])}
        arg_dict = {arg: inpt for (arg, inpt) in zip(genes[2], genes[3])}
        return entity_tester.EntityTestTask(
            entity=self.entity,
            method=self.method,
            field_dict=field_dict,
            arg_dict=arg_dict,
            config=self.config
        )

    def _create_gene_base(self):
        """Create a valid genetic base to evolve on"""
        # todo if dependencies allowed, firstly try to create without dependencies, for first x epochs

        # if dependencies are disabled remove fields that require dependencies
        if self.disable_dependencies:
            indict = self._etester.fields
            for exclusion in ['OneToOneField', 'OneToManyField']:
                indict = {
                    field: nailgun_obj
                    for field, nailgun_obj in indict.items()
                    if exclusion != nailgun_obj.__class__.__name__
                       and exclusion not in field
                }
            self._etester.fields = indict

        # create a list of fields
        # choose randomly how many fields is used for the gene
        fields = random.sample(list(self._etester.fields), random.randint(0, len(list(self._etester.fields))))
        nailgun_fields = [self._etester.fields[field].__class__.__name__ for field in fields]

        # TODO list field, dict field, float field, OneToManyField, OneToOneField
        # if the nailgun field is:
        # list choose a nailgun field, and random number and fill the list
        # dict is the same but use unique string as a key and random field as the value
        # float - create a float value as we do in nailgun
        # if there is oneToOneField the field has to be created first
        # if there is oneToManyField
        # example {"location_ids": ["2","381"]}

        # match random inputs to the previous list of fields based on the field type
        field_inputs = [
            self.config.RIZZA['GENETICS']['NAILGUN FIELDS TYPE MAPPING'][nailgun_field]
            for nailgun_field in nailgun_fields
        ]

        # create a list of random method inputs
        args = entity_tester.EntityTester.pull_args(self._method_inst)
        args = [random.choice(args) for _ in range(random.randint(0, len(args)))]
        # match random inputs to the previous list of args
        if 'create_missing' in args:
            len_args = len(args) -1
        else:
            len_args = len(args)
        arg_inputs = random.sample(
            list(self.config.RIZZA['GENETICS']['NAILGUN FIELDS TYPE MAPPING'].values()), len_args
        )

        # for nailgun the types match can be created, fauxfactory type gen_date matches with
        return [fields, field_inputs, args, arg_inputs]

    def run(self, mock=False, save_only_passed=False):
        """Run a population attempting to maximize desired results"""
        if not self._method_inst:
            logger.warning('{} does not have the method {}'.format(
                self.entity, self.method
            ))
            return None

        # Create our population
        try:
            population = genetics.Population(
                gene_base=[self._create_gene_base()],
                population_count=self.population_count,
                generator_function=self._create_gene_base,
                gene_length=1,
                mutate=False,
                rev_pop_sort=not self.seek_bad
            )
        except Exception as err:
            logger.error('Unable to create a population due to: {}'.format(
                err
            ))
            return False
        # Attempt to continue where we left off, if desired
        if not self.fresh:
            best = self._load_test()
            if best:
                population.population[0].genes = best

        for generation in range(self.max_generations):
            for organism in population.population:
                logger.debug('Testing {}'.format(organism))
                # create an entity_tester. from the organism
                task = self._genes_to_task(organism.genes)
                # execute the test task
                result = task.execute(mock)
                if 'pass' in result and not mock and not self.seek_bad:
                    self._save_organism(organism)
                    logger.info('Success! Generation {} passed with:\n{}'.format(
                        generation,
                        yaml.dump(
                            attr.asdict(
                                self._genes_to_task(organism.genes),
                                filter=lambda attr, value: attr.name != 'config'
                            ),
                            default_flow_style=False)
                    ))
                    return True
                # judge the results and pass those points to the organism
                organism.points = self._judge(result, mock)

            population.sort_population()
            logger.info('Generation {} best: {}'.format(
                generation, population.population[0]))
            # breed the current generation and iterate
            population.breed_population()
        if not mock and not save_only_passed:
            # save the current best in the config
            self._save_organism(population.population[0])

    def run_best(self):
        """Pull the best saved test, if any, run it, and return the id"""
        self.config.RIZZA['GENETICS']['ALLOW RECURSION'] = False
        self.config.RIZZA['GENETICS']['MAX GENERATIONS'] = 1
        test = self._load_test()
        if test:
            test = self._genes_to_task(test)
            logger.info('Creating {}...'.format(self.entity))
            result = test.execute()
            if 'pass' in result:
                return result['pass'].get('id', -1)
        return -1

@attr.s()
class AsyncGeneticEntityTester(GeneticEntityTester):
    """An asynchronous version of the GeneticEntityTester."""

    max_running = attr.ib(default=25)

    def __attrs_post_init__(self):
        """Setup our remaining helpers"""
        super().__attrs_post_init__()
        self.max_running = asyncio.Semaphore(self.max_running)
        self._results = asyncio.Queue()

    async def _run_org(self, organism, mock=False):
        async with self.max_running:
            task = super()._genes_to_task(organism.genes)
            # execute the test task
            try:
                result = await self.loop.run_in_executor(
                    # default exectutor, function, args
                    None, task.execute, mock)
            except Exception as err:
                logger.error(err)
                result = "Unhandled Exception"
            # judge the results and pass those points to the organism
        organism.points = super()._judge(result, mock)
        logger.debug('Tested {}'.format(organism))
        await self._results.put((result, organism))

    async def test_population(self, mock=False):
        """Run the tests passed in and return the log file"""
        tasks = [
            asyncio.ensure_future(self._run_org(org, mock))
            for org in self._population.population
        ]
        await asyncio.wait(tasks)

    def run(self, mock=False, save_only_passed=False):
        """Run a population attempting to maximize desired results"""
        if not self._method_inst:
            logger.warning('{} does not have the method {}'.format(
                self.entity, self.method
            ))
            return None

        # Create our population
        try:
            self._population = genetics.Population(
                gene_base=[self._create_gene_base()],
                population_count=self.population_count,
                generator_function=self._create_gene_base,
                gene_length=1,
                mutate=False,
                rev_pop_sort=not self.seek_bad
            )
        except Exception as err:
            logger.error('Unable to create a population due to: {}'.format(
                err
            ))
            return False
        # Attempt to continue where we left off, if desired
        if not self.fresh:
            best = super()._load_test()
            if best:
                self._population.population[0].genes = best

        for generation in range(self.max_generations):
            self.loop = asyncio.new_event_loop()
            self._results.empty()
            self.loop.run_until_complete(self.test_population(mock))
            self.loop.close()
            while self._results.qsize() > 0:
                result, organism = self._results.get_nowait()
                if 'pass' in result and not mock and not self.seek_bad:
                    logger.info('Success! Generation {} passed with:\n{}'.format(
                        generation,
                        yaml.dump(
                            attr.asdict(
                                super()._genes_to_task(organism.genes),
                                filter=lambda attr, value: attr.name != 'config'
                            ),
                            default_flow_style=False)
                    ))
                    super()._save_organism(organism)
                    return True

            self._population.sort_population()
            logger.info('Generation {} best: {}'.format(
                generation, self._population.population[0]))
            # breed the current generation and iterate
            self._population.breed_population()
        if not mock and not save_only_passed:
            # save the current best in the config
            super()._save_organism(self._population.population[0])
