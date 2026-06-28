"""Main module for rizza's interface."""
import contextlib
import logging
import sys

import pytest
from rich import print as rprint
from rich.syntax import Syntax
import rich_click as click
import yaml

from rizza import genetic_tester
from rizza.entity_tester import EntityTester
from rizza.helpers import prune as prune_helper
from rizza.helpers.config import Config

logger = logging.getLogger(__name__)

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def cli(ctx):
    """An increasingly intelligent automated product tester."""
    ctx.obj = Config()


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
@click.option(
    "--seek-bad", is_flag=True, help="Used to promote bad results, based on your config."
)
@click.option(
    "--disable-dependencies",
    is_flag=True,
    help="Stop rizza from creating required entities.",
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
@click.option("--cleanup", is_flag=True, help="Clean up created entities after test run.")
@click.option("--debug", is_flag=True, help="Enable debug logging level.")
@click.pass_context
def genetic(
    ctx,
    entity,
    method,
    seek_bad,
    disable_dependencies,
    run_async,
    async_limit,
    fresh,
    prune,
    cleanup,
    debug,
):
    """Use genetic algorithms to learn how to use an entity's method."""
    conf = ctx.obj
    args_dict = {
        "entity": entity,
        "method": method,
        "seek_bad": seek_bad,
        "disable_dependencies": disable_dependencies,
        "run_async": run_async,
        "async_limit": async_limit,
        "fresh": fresh,
        "prune": prune,
        "cleanup": cleanup,
        "debug": debug,
    }
    conf.load_cli_args(type("Args", (), args_dict), command=True)

    if prune:
        conf.init_logger(
            path=conf.base_dir.joinpath("logs/prune.log"),
            level="debug" if debug else None,
        )
        if run_async and entity == "All":
            prune_helper.async_genetic_prune(conf, entity, async_limit)
        else:
            prune_helper.genetic_prune(conf, entity)
    elif entity == "All":
        conf.init_connection()
        genetic_tester.run_all_entities(
            debug=debug,
            async_mode=run_async,
            config=conf,
            entity=entity,
            method=method,
            disable_dependencies=disable_dependencies,
            seek_bad=seek_bad,
            fresh=fresh,
            max_running=async_limit,
        )
    elif run_async:
        conf.init_connection()
        gtester = genetic_tester.AsyncGeneticEntityTester(
            config=conf,
            entity=entity,
            method=method,
            disable_dependencies=disable_dependencies,
            seek_bad=seek_bad,
            fresh=fresh,
            max_running=async_limit,
        )
        conf.init_logger(
            path=conf.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
            level="debug" if debug else None,
        )
        gtester.run()
        if cleanup:
            from rizza import apix_loader

            apix_loader.get_satellite_class()().clean_session()
    else:
        conf.init_connection()
        gtester = genetic_tester.GeneticEntityTester(
            config=conf,
            entity=entity,
            method=method,
            disable_dependencies=disable_dependencies,
            seek_bad=seek_bad,
            fresh=fresh,
        )
        conf.init_logger(
            path=conf.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
            level="debug" if debug else None,
        )
        gtester.run()
        if cleanup:
            from rizza import apix_loader

            apix_loader.get_satellite_class()().clean_session()


@cli.group()
@click.pass_context
def config(ctx):
    """Manage rizza configurations."""
    pass


@config.command()
@click.argument("chunk", required=False, default=None)
@click.pass_context
def view(ctx, chunk):
    """View the full config or a specific chunk (e.g. genetics.criteria.pass)."""
    conf = ctx.obj
    try:
        value = conf.get_chunk(chunk)
    except KeyError as e:
        click.echo(str(e), err=True)
        return
    if isinstance(value, dict):
        yaml_string = yaml.dump(value, default_flow_style=False)
        rprint(Syntax(yaml_string, "yaml", theme="native", line_numbers=True))
    else:
        rprint(value)


@config.command(name="set")
@click.argument("chunk")
@click.argument("value")
@click.pass_context
def config_set(ctx, chunk, value):
    """Set a config value by chunk path (e.g. connection.hostname myhost.example.com)."""
    conf = ctx.obj
    try:
        conf.set_chunk(chunk, value)
    except KeyError as e:
        click.echo(str(e), err=True)
        return
    click.echo(f"Set {chunk} = {yaml.safe_load(str(value))!r}")


@config.command(name="init")
@click.option("--force", is_flag=True, help="Overwrite existing config files.")
@click.pass_context
def config_init(ctx, force):
    """Initialize config files from bundled examples."""
    conf = ctx.obj
    result = conf.init_config(force=force)
    if result["copied"]:
        click.echo(f"Created: {', '.join(result['copied'])}")
    if result["skipped"]:
        skipped = ", ".join(result["skipped"])
        click.echo(f"Skipped (already exist): {skipped} (use --force to overwrite)")


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
    from rizza import apix_loader

    lib_path = getattr(conf.rizza, "apix_lib_path", None)
    if lib_path:
        with contextlib.suppress(FileNotFoundError):
            apix_loader.get_apix_module(path=lib_path)
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
        logger.exception(f"An unexpected error occurred: {err}")
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)
