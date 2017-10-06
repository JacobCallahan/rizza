# -*- encoding: utf-8 -*-
"""Main module for rizza's interface."""
import argparse, pytest, sys
from nailgun.config import ServerConfig
from fauxfactory import gen_uuid
from rizza.entity_tester import EntityTester
from rizza.task_manager import TaskManager


class Main(object):

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "action", type=str, choices=['brute', 'config', 'list', 'test'],
            help="The action to perform.")
        args = parser.parse_args(sys.argv[1:2])
        if not hasattr(self, args.action):
            print('Action {0} is not supported.'.format(args.action))
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
            "-l", "--log-path", type=str,
            default="session{0}.log".format(gen_uuid()[:8]),
            help="The file path to write test results to.")
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

        args = parser.parse_args(sys.argv[2:])
        if args.import_path:
            tests = TaskManager.import_tasks(args.import_path)
            if args.log_path.lower() == 'stdout':
                for test in tests:
                    print("Running test task {0}".format(test))
                    print(test.execute())
            else:
                TaskManager.log_tests(args.log_path, tests=tests)
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
                elif args.log_path.lower() == 'stdout':
                    for test in tests:
                        print("Running test task {0}".format(test))
                        print(test.execute())
                else:
                    TaskManager.log_tests(args.log_path, tests=tests)

    def config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("project", type=str, choices=['nailgun'])
        parser.add_argument("-u", "--user", type=str,
            help="Username")
        parser.add_argument("-p", "--password", type=str,
            help="Password")
        parser.add_argument("-t", "--target", type=str,
            help="The target Satellite's URL (https://server.domain.com)")
        parser.add_argument("--verify", action="store_true",
            help="Disable or enable SSL verification (default: False)")
        parser.add_argument("--label", type=str, default='default',
            help="The configuration label to use.")
        parser.add_argument("--path", type=str,
            help="The configuration file path to use.")
        parser.add_argument("--clear", action="store_true",
            help="Clear existing configuration.")
        parser.add_argument("--show", action="store_true",
            help="Show existing configuration.")

        args = parser.parse_args(sys.argv[2:])
        cfg_path = args.path or None

        if args.project == 'nailgun':
            if args.show:
                print(ServerConfig(url='').get())

            if args.clear:
                server_conf.save(label=args.label, path=cfg_path)
            try:

                server_conf = server_conf.get(label=args.label, path=cfg_path)
            except Exception:
                if not args.user or not args.password or not args.target:
                    print("Unable to find saved nailgun configuration. "
                           "Please specify a user, password, and target.")
                    return 1

            if args.user or args.password:
                if args.user and args.password:
                    server_conf.auth = (args.user, args.password)
                elif args.user and server_conf.auth:
                    server_conf.auth = (args.user, server_conf.auth[1])
                elif args.password and server_conf.auth:
                    server_conf.auth = (server_conf.auth[0], args.password)
                else:
                    print('Couldn`t set the auth. Pass a user and password')

            if args.target:
                server_conf.url = args.target
            server_conf.verify = args.verify
            server_conf.save(label=args.label, path=cfg_path)
            print("Server config saved.")

    def list(self):
        """List out some information about our entities and inputs."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "subject", type=str,
            choices=['entities', 'methods', 'fields', 'input-methods'])
        parser.add_argument(
            "-e", "--entity", type=str,
            help="The name of the entity you want to filter by.")
        parser.add_argument(
            "-m", "--method", type=str,
            help="The name of the method you want to filter by.")

        args = parser.parse_args(sys.argv[2:])
        if args.subject == 'entities':
            print(", ".join(EntityTester.pull_entities().keys()))
        elif args.subject == 'input-methods':
            print(", ".join(EntityTester.pull_input_methods().keys()))
        elif args.entity in EntityTester.pull_entities():
            entity = EntityTester.pull_entities()[args.entity]
            if args.subject == 'methods':
                print(", ".join(EntityTester.pull_methods(entity).keys()))
            elif args.subject == 'fields':
                method = EntityTester.pull_methods(entity).get(args.method, None)
                if method:
                    print(", ".join(EntityTester.pull_args(method)))
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
    Main()
