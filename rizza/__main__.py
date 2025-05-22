"""Main module for rizza's interface."""
from pathlib import Path
import sys

from fauxfactory import gen_uuid
from logzero import logger
import pytest
from rich import print as rprint
from rich.syntax import Syntax
import rich_click as click
import yaml

from rizza import genetic_tester
from rizza.entity_tester import EntityTester
from rizza.helpers import prune
from rizza.helpers.config import Config
from rizza.task_manager import AsyncTaskManager, TaskManager

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def cli(ctx):
    """An increasingly intelligent automated product tester."""
    ctx.obj = Config()


@cli.command()
@click.option(
    "-e",
    "--entities",
    type=str,
    multiple=True,
    help="The name of the entity(s) you want to test (Product; All).",
)
@click.option(
    "-o", "--output-path", type=click.Path(), help="The file path to write the test tasks to."
)
@click.option(
    "-i", "--import-path", type=click.Path(), help="The file path to exported test tasks."
)
@click.option(
    "-l",
    "--log-name",
    type=str,
    default=f"session{gen_uuid()[:8]}.log",
    show_default=True,
    help="The file name to write test results to.",
)
@click.option("--max-fields", type=int, help="The maximum number of entity fields to use.")
@click.option("--max-inputs", type=int, help="The maximum number of input methods to use.")
@click.option(
    "--field-exclude",
    type=str,
    multiple=True,
    help="One or more fields to exclude from brute force testing. (e.g. 'label id')",
)
@click.option(
    "--method-exclude",
    type=str,
    multiple=True,
    help=(
        "One or more methods to exclude from brute force testing. "
        "(e.g. 'raw search read get payload')"
    ),
)
@click.option("--run-async", is_flag=True, help="Run tests asynchronously.")
@click.option(
    "--async-limit",
    type=int,
    default=100,
    show_default=True,
    help="The maximum number of tests to run asynchronously.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging level.")
@click.pass_context
def brute(
    ctx,
    entities,
    output_path,
    import_path,
    log_name,
    max_fields,
    max_inputs,
    field_exclude,
    method_exclude,
    run_async,
    async_limit,
    debug,
):
    """Run the brute force testing."""
    conf = ctx.obj
    # Create a pseudo-args object for compatibility with existing conf.load_cli_args
    args_dict = {
        "entities": entities,
        "output_path": output_path,
        "import_path": import_path,
        "log_name": log_name,
        "max_fields": max_fields,
        "max_inputs": max_inputs,
        "field_exclude": field_exclude,
        "method_exclude": method_exclude,
        "run_async": run_async,
        "async_limit": async_limit,
        "debug": debug,
    }
    conf.load_cli_args(type("Args", (), args_dict), command=True)
    conf.init_logger(
        path=conf.base_dir.joinpath(f"logs/brute/{log_name}"),
        level="debug" if debug else None,
    )

    if import_path:
        if run_async:
            AsyncTaskManager(import_path, async_limit).run_tests()
        else:
            tests = TaskManager.import_tasks(Path(import_path))
            TaskManager.run_tests(tests=tests)
    else:
        for entity_name in entities:
            e_tester = EntityTester(entity_name)
            e_tester.prep(field_exclude=list(field_exclude), method_exclude=list(method_exclude))
            tests = e_tester.brute_force(max_fields=max_fields, max_inputs=max_inputs)
            if output_path:
                TaskManager.export_tasks(path=Path(output_path), tasks=tests)
            elif run_async:
                AsyncTaskManager(tests, async_limit).run_tests()
            else:
                TaskManager.run_tests(tests=tests)


@cli.command()
@click.option(
    "-e",
    "--entity",
    type=str,
    required=True,
    help="The name of the entity you want to test (Organization).",
)
@click.option(
    "-m",
    "--method",
    type=str,
    default="create",
    show_default=True,
    help="The name of the method you want to test (create).",
)
@click.option("--population-count", type=int, help="The number of organisms in each generation.")
@click.option("--max-generations", type=int, help="The maximum number of generations to run.")
@click.option(
    "--max-recursive-generations",
    type=int,
    help="The maximum number of recursive generations to run.",
)
@click.option(
    "--max-recursive-depth", type=int, help="Limit recursive dependency resolution depth."
)
@click.option(
    "--seek-bad", is_flag=True, help="Used to promote bad results, based on your config."
)
@click.option(
    "--disable-dependencies",
    is_flag=True,
    help="Stop rizza from creating required entities.",
)
@click.option(
    "--disable-recursion",
    is_flag=True,
    help="Stop rizza from attempting to create required entities.",
)
@click.option("--run-async", is_flag=True, help="Run tests asynchronously.")
@click.option(
    "--async-limit",
    type=int,
    default=100,
    show_default=True,
    help="The maximum number of tests to run asynchronously. (default is 100)",
)
@click.option("--fresh", is_flag=True, help="Don't attempt to load in saved results.")
@click.option(
    "--prune",
    is_flag=True,
    help="Remove positive tests that don't pass. Can specify 'All' for entity",
)
@click.option("--debug", is_flag=True, help="Enable debug logging level.")
@click.pass_context
def genetic(
    ctx,
    entity,
    method,
    population_count,
    max_generations,
    max_recursive_generations,
    max_recursive_depth,
    seek_bad,
    disable_dependencies,
    disable_recursion,
    run_async,
    async_limit,
    fresh,
    prune_flag,  # renamed from prune to avoid conflict with helpers.prune
    debug,
):
    """Use genetic algorithms to learn how to use an entity's method."""
    conf = ctx.obj
    args_dict = {
        "entity": entity,
        "method": method,
        "population_count": population_count,
        "max_generations": max_generations,
        "max_recursive_generations": max_recursive_generations,
        "max_recursive_depth": max_recursive_depth,
        "seek_bad": seek_bad,
        "disable_dependencies": disable_dependencies,
        "disable_recursion": disable_recursion,
        "run_async": run_async,
        "async_limit": async_limit,
        "fresh": fresh,
        "prune": prune_flag,
        "debug": debug,
    }
    conf.load_cli_args(type("Args", (), args_dict), command=True)

    if prune_flag:
        conf.init_logger(
            path=conf.base_dir.joinpath("logs/prune.log"),
            level="debug" if debug else None,
        )
        if run_async and entity == "All":
            prune.async_genetic_prune(conf, entity, async_limit)
        else:
            prune.genetic_prune(conf, entity)
    elif entity == "All":
        genetic_tester.run_all_entities(
            debug=debug,
            async_mode=run_async,
            config=conf,
            entity=entity,
            method=method,
            population_count=population_count,
            max_generations=max_generations,
            max_recursive_generations=max_recursive_generations,
            max_recursive_depth=max_recursive_depth,
            disable_dependencies=disable_dependencies,
            disable_recursion=disable_recursion,
            seek_bad=seek_bad,
            fresh=fresh,
            max_running=async_limit,
        )
    elif run_async:
        gtester = genetic_tester.AsyncGeneticEntityTester(
            config=conf,
            entity=entity,
            method=method,
            population_count=population_count,
            max_generations=max_generations,
            max_recursive_generations=max_recursive_generations,
            max_recursive_depth=max_recursive_depth,
            disable_dependencies=disable_dependencies,
            disable_recursion=disable_recursion,
            seek_bad=seek_bad,
            fresh=fresh,
            max_running=async_limit,
        )
        conf.init_logger(
            path=conf.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
            level="debug" if debug else None,
        )
        gtester.run()
    else:
        gtester = genetic_tester.GeneticEntityTester(
            config=conf,
            entity=entity,
            method=method,
            population_count=population_count,
            max_generations=max_generations,
            max_recursive_generations=max_recursive_generations,
            max_recursive_depth=max_recursive_depth,
            disable_dependencies=disable_dependencies,
            disable_recursion=disable_recursion,
            seek_bad=seek_bad,
            fresh=fresh,
        )
        conf.init_logger(
            path=conf.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
            level="debug" if debug else None,
        )
        gtester.run()


@cli.group()
@click.pass_context
def config(ctx):
    """Manage rizza configurations."""
    pass  # ctx.obj (Config) is already set from the main cli group


@config.command()
@click.option("--path", type=click.Path(), help="The configuration file path to use.")
@click.option("--clear", is_flag=True, help="Clear existing configuration.")
@click.option("--show", is_flag=True, help="Show existing configuration.")
@click.pass_context
def rizza(ctx, path, clear, show):
    """Configure rizza settings."""
    conf = ctx.obj
    args_dict = {
        "project": "rizza",
        "path": path,
        "clear": clear,
        "show": show,
    }
    conf.load_cli_args(type("Args", (), args_dict))

    if show:
        # conf.yaml_print(conf.RIZZA)
        yaml_string = yaml.dump(conf.RIZZA)
        rprint(Syntax(yaml_string, "yaml", theme="native", line_numbers=True))
    if clear:
        conf.clear_rizza()


@cli.command(name="list")  # Renamed to avoid conflict with Python's list
@click.argument(
    "subject", type=click.Choice(["entities", "methods", "fields", "args", "input-methods"])
)
@click.option("-e", "--entity", type=str, help="The name of the entity you want to filter by.")
@click.option("-m", "--method", type=str, help="The name of the method you want to filter by.")
@click.pass_context
def list_cmd(ctx, subject, entity, method):
    """List out information about entities and inputs."""
    conf = ctx.obj
    # Create a pseudo-args object
    args_dict = {
        "subject": subject,
        "entity": entity,
        "method": method,
    }
    conf.load_cli_args(type("Args", (), args_dict))
    _list_subject(subject, entity, method)


def _list_subject(subject, entity_name, method_name):
    """Helper function to handle listing logic for different subjects."""
    if subject == "entities":
        _list_entities()
    elif subject == "input-methods":
        _list_input_methods()
    else:
        _list_entity_details(subject, entity_name, method_name)


def _list_entities():
    """List all available entities."""
    entities_list = list(EntityTester.pull_entities().keys())
    if entities_list:
        for item in entities_list:
            rprint(item)
    else:
        click.echo("No entities found.")


def _list_input_methods():
    """List all available input methods."""
    input_methods_list = list(EntityTester.pull_input_methods().keys())
    if input_methods_list:
        for item in input_methods_list:
            rprint(item)
    else:
        click.echo("No input methods found.")


def _list_entity_details(subject, entity_name, method_name):
    """List details (methods, fields, args) for a specific entity."""
    pulled_entities = EntityTester.pull_entities()
    if entity_name not in pulled_entities:
        click.echo(f"Entity '{entity_name}' not found.", err=True)
        return

    entity_data = pulled_entities[entity_name]
    if subject == "methods":
        _list_entity_methods(entity_data, entity_name)
    elif subject == "fields":
        _list_entity_fields(entity_data, entity_name)
    elif subject == "args":
        _list_method_args(entity_data, entity_name, method_name)
    else:
        # Should not happen due to click.Choice
        click.echo(f"Unknown subject '{subject}' for entity listing.", err=True)


def _list_entity_methods(entity_data, entity_name):
    """List methods for a given entity."""
    methods_list = list(EntityTester.pull_methods(entity_data).keys())
    if methods_list:
        for item in methods_list:
            rprint(item)
    else:
        click.echo(f"No methods found for entity '{entity_name}'.")


def _list_entity_fields(entity_data, entity_name):
    """List fields for a given entity."""
    fields_list = list(EntityTester.pull_fields(entity_data).keys())
    if fields_list:
        for item in fields_list:
            rprint(item)
    else:
        click.echo(f"No fields found for entity '{entity_name}'.")


def _list_method_args(entity_data, entity_name, method_name):
    """List arguments for a specific method of an entity."""
    method_data = EntityTester.pull_methods(entity_data).get(method_name, None)
    if method_data:
        args_list = EntityTester.pull_args(method_data)
        if args_list:
            for item in args_list:
                rprint(item)
        else:
            click.echo(f"No arguments found for method '{method_name}' in entity '{entity_name}'.")
    else:
        click.echo(f"Method '{method_name}' not found for entity '{entity_name}'.", err=True)


@cli.command()
@click.option(
    "--args",
    "pytest_args",  # renamed to avoid conflict
    type=str,
    multiple=True,
    help='pytest args to pass in. (e.g. --args="-r a" --args="tests/specific_test.py")',
)
def test(pytest_args):
    """Run pytest tests."""
    pyargs = list(pytest_args) if pytest_args else ["-q"]
    errno = pytest.cmdline.main(args=pyargs)
    sys.exit(errno)


if __name__ == "__main__":
    try:
        cli(obj=None)  # obj=None because Config is created in cli's callback and passed via ctx
    except KeyboardInterrupt:
        logger.warning("Rizza stopped by user.")
    except Exception as err:
        # Log the error using logzero
        logger.error(f"An unexpected error occurred: {err}", exc_info=True)
        # Optionally, print a user-friendly message to stderr
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)
