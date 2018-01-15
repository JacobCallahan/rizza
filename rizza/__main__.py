# -*- encoding: utf-8 -*-
"""Main module for rizza's interface."""
import argparse
import sys
import pytest
from fauxfactory import gen_uuid
from logzero import logger
from nailgun.config import ServerConfig
from rizza.entity_tester import EntityTester
from rizza.genetic_tester import GeneticEntityTester
from rizza.helpers.config import Config
from rizza.helpers import prune
from rizza.task_manager import TaskManager


class Main(object):
    """This main class will allow for better nested arguments (git stlye)"""
    def __init__(self):
        self.conf = Config()
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "action", type=str, choices=[
                'brute', 'genetic', 'config', 'list', 'test'],
            help="The action to perform.")
        args = parser.parse_args(sys.argv[1:2])
        if not hasattr(self, args.action):
            logger.warning('Action {0} is not supported.'.format(args.action))
            parser.print_help()
            exit(1)
        getattr(self, args.action)()

    def brute(self):
        """Run the brute force thing."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-e", "--entities", type=str, nargs='+',
            help="The name of the entity(s) you want to test (Product; All).")
        parser.add_argument(
            "-o", "--output-path", type=str,
            help="The file path to write the test tasks to.")
        parser.add_argument(
            "-i", "--import-path", type=str,
            help="The file path to exported test tasks.")
        parser.add_argument(
            "-l", "--log-name", type=str,
            default="session{0}.log".format(gen_uuid()[:8]),
            help="The file name to write test results to.")
        parser.add_argument(
            "--max-fields", type=int,
            help="The maximum number of entity fields to use.")
        parser.add_argument(
            "--max-inputs", type=int,
            help="The maximum number of input methods to use.")
        parser.add_argument(
            "--field-exclude", type=str, nargs='+',
            help="One or more fields to exclude from brute force testing. "
            "(e.g. 'label id'")
        parser.add_argument(
            "--method-exclude", type=str, nargs='+',
            help="One or more methods to exclude from brute force testing. "
            "(e.g. 'raw search read get payload')")
        parser.add_argument(
            "--debug", action="store_true",
            help="Enable debug loggin level.")

        args = parser.parse_args(sys.argv[2:])
        self.conf.load_cli_args(args, command=True)
        self.conf.init_logger(
            path='logs/{}'.format(args.log_name),
            level='debug' if args.debug else None
        )

        if args.import_path:
            tests = TaskManager.import_tasks(args.import_path)
            TaskManager.run_tests(tests=tests)
        else:
            for entity in args.entities:
                e_tester = EntityTester(entity)
                e_tester.prep(
                    field_exclude=args.field_exclude,
                    method_exclude=args.method_exclude
                )
                tests = e_tester.brute_force(
                    max_fields=args.max_fields,
                    max_inputs=args.max_inputs
                )
                if args.output_path:
                    TaskManager.export_tasks(
                        path=args.output_path, tasks=tests)
                else:
                    TaskManager.run_tests(tests=tests)

    def genetic(self):
        """Use genetic algorithms to successfully learn how to use an
        entity's method.
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-e", "--entity", type=str, required=True,
            help="The name of the entity you want to test (Organization).")
        parser.add_argument(
            "-m", "--method", type=str, default='create',
            help="The name of the method you want to test (create).")
        parser.add_argument(
            "--population-count", type=int, default=None,
            help="The number of organisms in each generation.")
        parser.add_argument(
            "--max-generations", type=int, default=None,
            help="The maximum number of generations to run.")
        parser.add_argument(
            "--max-recursive-generations", type=int, default=None,
            help="The maximum number of recursive generations to run.")
        parser.add_argument(
            "--max-recursive-depth", type=int, default=None,
            help="Limit recursive dependency resolution depth.")
        parser.add_argument(
            "--seek-bad", action="store_true",
            help="Used to promote bad results, based on your config.")
        parser.add_argument(
            "--disable-recursion", action="store_true",
            help="Stop rizza from attempting to create required entities.")
        parser.add_argument(
            "--fresh", action="store_true",
            help="Don't attempt to load in saved results.")
        parser.add_argument(
            "--prune", action="store_true", help="Remove positive tests that "
            "don't pass. Can specify 'All' for entity")
        parser.add_argument(
            "--debug", action="store_true",
            help="Enable debug loggin level.")

        args = parser.parse_args(sys.argv[2:])
        self.conf.load_cli_args(args, command=True)

        if args.prune:
            self.conf.init_logger(
                path='logs/prune.log', level='debug' if args.debug else None
            )
            prune.genetic_prune(self.conf, args.entity)
        else:
            gtester = GeneticEntityTester(
                config=self.conf,
                entity=args.entity,
                method=args.method,
                population_count=args.population_count,
                max_generations=args.max_generations,
                max_recursive_generations=args.max_recursive_generations,
                max_recursive_depth=args.max_recursive_depth,
                disable_recursion=args.disable_recursion,
                seek_bad=args.seek_bad,
                fresh=args.fresh
            )
            self.conf.init_logger(
                path='logs/{}.log'.format(gtester.test_name),
                level='debug' if args.debug else None
            )
            gtester.run()

    def config(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="project",
            help="The component's config you want to change or view.")
        nailgun_config = subparsers.add_parser('nailgun')
        nailgun_config.add_argument("-u", "--user", type=str,
            help="Username")
        nailgun_config.add_argument("-p", "--password", type=str,
            help="Password")
        nailgun_config.add_argument("-t", "--target", type=str,
            help="The target Satellite's URL (https://server.domain.com)")
        nailgun_config.add_argument("--verify", action="store_true",
            help="Disable or enable SSL verification (default: False)")
        nailgun_config.add_argument("--label", type=str, default='default',
            help="The configuration label to use.")
        nailgun_config.add_argument("--path", type=str,
            help="The configuration file path to use.")
        nailgun_config.add_argument("--clear", action="store_true",
            help="Clear existing configuration.")
        nailgun_config.add_argument("--show", action="store_true",
            help="Show existing configuration.")

        rizza_config = subparsers.add_parser('rizza')
        rizza_config.add_argument("--path", type=str,
            help="The configuration file path to use.")
        rizza_config.add_argument("--clear", action="store_true",
            help="Clear existing configuration.")
        rizza_config.add_argument("--show", action="store_true",
            help="Show existing configuration.")

        args = parser.parse_args(sys.argv[2:])
        self.conf.load_cli_args(args)
        cfg_path = args.path or None

        if args.project == 'nailgun':
            if args.show:
                self.conf.yaml_print(self.conf.NAILGUN)
            if args.clear:
                self.conf.clear_nailgun()
        elif args.project == 'rizza':
            if args.show:
                self.conf.yaml_print(self.conf.RIZZA)
            if args.clear:
                self.conf.clear_rizza()

    def list(self):
        """List out some information about our entities and inputs."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "subject", type=str,
            choices=['entities', 'methods', 'fields', 'args', 'input-methods'])
        parser.add_argument(
            "-e", "--entity", type=str,
            help="The name of the entity you want to filter by.")
        parser.add_argument(
            "-m", "--method", type=str,
            help="The name of the method you want to filter by.")

        args = parser.parse_args(sys.argv[2:])
        self.conf.load_cli_args(args)
        if args.subject == 'entities':
            print(" ".join(EntityTester.pull_entities().keys()))
        elif args.subject == 'input-methods':
            print(" ".join(EntityTester.pull_input_methods().keys()))
        elif args.entity in EntityTester.pull_entities():
            entity = EntityTester.pull_entities()[args.entity]
            if args.subject == 'methods':
                print(" ".join(EntityTester.pull_methods(entity).keys()))
            elif args.subject == 'fields':
                print(" ".join(EntityTester.pull_fields(entity).keys()))
            elif args.subject == 'args':
                method = EntityTester.pull_methods(entity).get(args.method, None)
                if method:
                    print(" ".join(EntityTester.pull_args(method)))
                else:
                    print('I\'m not aware of the method you specified.')
        else:
            print('The entity you specified was not in those I am aware of.')

    def test(self):
        """List out some information about our entities and inputs."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--args", type=str, nargs='+',
            help='pytest args to pass in. (--args="-r a")')
        args = parser.parse_args(sys.argv[2:])
        if args.args:
            pyargs = args.args
        else:
            pyargs=['-q']
        pytest.cmdline.main(args=pyargs)

    def __repr__(self):
        return None

if __name__ == '__main__':
    try:
        Main()
    except KeyboardInterrupt:
        logger.warning('Rizza stopped by user.')
    except Exception as err:
        logger.error(err)
