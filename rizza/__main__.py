"""Main module for rizza's interface."""

import contextlib
import datetime
import json
import logging
import os
from pathlib import Path
import signal
import sys

from rich import print as rprint
from rich.rule import Rule
from rich.syntax import Syntax
import rich_click as click
import yaml

from rizza import genetic_tester
from rizza.entity_tester import EntityTester
from rizza.helpers import prune as prune_helper
from rizza.helpers.config import Config
from rizza.helpers.logging import console

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
    default="_all",
    show_default=True,
    help="Entity to explore (_all for every entity).",
)
@click.option(
    "-m",
    "--method",
    type=str,
    default="_new",
    show_default=True,
    help="Method to explore (_new for untested, _all for every method).",
)
@click.option("--seek-bad", is_flag=True, help="Promote bad results, based on your config.")
@click.option(
    "--disable-dependencies",
    is_flag=True,
    help="Stop rizza from creating required entities.",
)
@click.option("--no-async", "no_async", is_flag=True, help="Run tests synchronously.")
@click.option(
    "--async-limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum number of tests to run concurrently.",
)
@click.option("--fresh", is_flag=True, help="Don't attempt to load in saved results.")
@click.option("--from-entity", help="Continue exploring alphabetically from the specified entity.")
@click.option(
    "-c",
    "--continue",
    "continue_run",
    is_flag=True,
    default=False,
    help="Resume from the last checkpointed entity/method in ~/rizza/data/explore_checkpoint_*.",
)
@click.option(
    "--last-failed",
    is_flag=True,
    default=False,
    help="Re-explore entity/method pairs recorded in ~/rizza/validation/last_failed.json.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging level.")
@click.pass_context
def explore(
    ctx,
    entity,
    method,
    seek_bad,
    disable_dependencies,
    no_async,
    async_limit,
    fresh,
    from_entity,
    continue_run,
    last_failed,
    debug,
):
    """Use genetic algorithms to explore an entity's methods."""
    from rizza.helpers.method_resolver import resolve_methods

    conf = ctx.obj
    run_async = not no_async

    conf.init_connection()

    # _all entity: delegate to run_all_entities with method-mode support
    if entity == "_all":
        if last_failed:
            interface = getattr(conf.rizza, "interface", "api")
            failed_file = (
                conf.base_dir / "validation" / f"last_failed_{conf.product_slug}_{interface}.json"
            )
            if not failed_file.exists():
                click.echo("No last_failed.json found. Run `rizza validate` first.", err=True)
                sys.exit(1)
            failed_map = json.loads(failed_file.read_text())
            genetic_tester.run_failed_entities(
                failed_map,
                debug=debug,
                async_mode=run_async,
                config=conf,
                disable_dependencies=disable_dependencies,
                seek_bad=seek_bad,
                fresh=fresh,
                max_running=async_limit,
            )
            return

        from_method = None
        if continue_run:
            from_entity, from_method = conf.load_checkpoint()
            if not from_entity:
                click.echo("No checkpoint found — starting from the beginning.")

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
            from_entity=from_entity,
            from_method=from_method,
        )
        return

    # Single entity: resolve methods here
    pulled_entities = EntityTester.pull_entities()
    entity_cls = pulled_entities.get(entity)
    if not entity_cls:
        click.echo(f"Entity '{entity}' not found.", err=True)
        sys.exit(1)

    methods = resolve_methods(conf, entity, entity_cls, method, seek_bad)
    if not methods:
        click.echo(f"All methods for '{entity}' already explored. Nothing to run.")
        return

    explored = 0
    for method_name in methods:
        if run_async:
            gtester = genetic_tester.AsyncGeneticEntityTester(
                config=conf,
                entity=entity,
                method=method_name,
                disable_dependencies=disable_dependencies,
                seek_bad=seek_bad,
                fresh=fresh,
                max_running=async_limit,
            )
        else:
            gtester = genetic_tester.GeneticEntityTester(
                config=conf,
                entity=entity,
                method=method_name,
                disable_dependencies=disable_dependencies,
                seek_bad=seek_bad,
                fresh=fresh,
            )
        conf.init_logger(
            path=conf.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
            level="debug" if debug else None,
        )
        gtester.run()
        explored += 1
    logger.info(f"Finished exploring {entity}! ({explored}/{len(methods)} methods attempted)")


def _format_test_label(test_name: str) -> str:
    """Convert 'Entity method mode' → 'Entity::method:mode' for display."""
    parts = test_name.split(" ", 2)
    if len(parts) == 3:
        return f"{parts[0]}::{parts[1]}:{parts[2]}"
    return test_name


def _sanitize(obj):
    """Recursively make an object safe for yaml.safe_dump / json.dumps.

    Converts tuples to lists and bytes to decoded strings so that the YAML
    output contains no Python-specific tags (!!python/tuple, !!binary, etc.)
    and no awkward single-quoted escapes.
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)
    if not isinstance(obj, str | int | float | bool | type(None)):
        return str(obj)
    return obj


def _copy_passing_tests(conf, results, from_version):
    """Copy passing test entries from a source version's YAML files into the current version."""
    source_dir = conf.genetic_tests_dir_for_version(from_version)
    dest_dir = conf.genetic_tests_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for r in results:
        if not r["passed"]:
            continue
        entity_name = r["entity"]
        test_name = r["test_name"]
        src_file = source_dir / f"{entity_name}.yaml"
        dst_file = dest_dir / f"{entity_name}.yaml"
        if not src_file.exists():
            continue
        src_tests = yaml.safe_load(src_file.read_text()) or {}
        if test_name not in src_tests:
            continue
        dst_tests = yaml.safe_load(dst_file.read_text()) if dst_file.exists() else {}
        dst_tests[test_name] = src_tests[test_name]
        with dst_file.open("w") as fh:
            yaml.dump(dst_tests, fh, default_flow_style=False)
        copied += 1
    click.echo(f"Copied {copied} test(s) to {dest_dir}")


def _write_validation_report(
    conf, results, report_path, report_format, entity="_all", method="_all"
):
    """Write a validation report to disk.

    :param conf: Config instance (used to derive product name and default path).
    :param results: List of validation result dicts from validate_tests().
    :param report_path: Override path string, or None to auto-generate.
    :param report_format: "yaml" or "json".
    :param entity: Entity filter used during validation (affects auto filename).
    :param method: Method filter used during validation (affects auto filename).
    :returns: Path object where the report was written.
    """
    import json as _json

    interface = getattr(conf.rizza, "interface", "api")
    product = getattr(conf.rizza, "product_name", "satellite")
    version = conf.product_version_minor
    date_str = datetime.date.today().strftime("%d%b%y")

    if report_path is None:
        out_dir = conf.base_dir / "validation"
        out_dir.mkdir(parents=True, exist_ok=True)
        parts = [product, version, interface]
        if entity not in ("_all", None):
            parts.append(entity)
        if method not in ("_all", "_new", None):
            parts.append(method)
        stem = "-".join(parts)
        dest = out_dir / f"{stem}-{date_str}.{report_format}"
    else:
        dest = Path(report_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.suffix == ".json":
            report_format = "json"
        elif dest.suffix in (".yaml", ".yml"):
            report_format = "yaml"

    passed_count = sum(1 for r in results if r["passed"])
    payload = _sanitize(
        {
            "product": product,
            "version": version,
            "interface": interface,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "summary": {
                "total": len(results),
                "passed": passed_count,
                "failed": len(results) - passed_count,
            },
            "tests": results,
        }
    )

    if report_format == "json":
        dest.write_text(_json.dumps(payload, indent=2, default=str))
    else:
        with dest.open("w") as fh:
            yaml.safe_dump(payload, fh, default_flow_style=False, allow_unicode=True)

    return dest


def _print_validation_summary(results, prune, report_dest=None):
    """Print a rich results table and summary after validation completes."""
    if not results:
        console.print("\n[dim]No saved tests found.[/dim]")
        return

    # Results table
    console.print()
    max_label = max(len(_format_test_label(r["test_name"])) for r in results)
    for r in results:
        label = _format_test_label(r["test_name"])
        if r["passed"]:
            console.print(f"  [green]{label:<{max_label}}[/green]  PASS")
        else:
            pruned_tag = "  [dim][pruned][/dim]" if prune else ""
            console.print(f"  [red]{label:<{max_label}}[/red]  FAIL{pruned_tag}")

    # Separator + summary
    console.print(Rule(style="dim"))
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    total = len(results)

    parts = []
    if passed:
        parts.append(f"[bold green]{passed} passed[/bold green]")
    if failed:
        parts.append(f"[bold red]{failed} failed[/bold red]")
    if prune and failed:
        parts.append(f"[dim]{failed} pruned[/dim]")
    parts.append(f"[dim]{total} total[/dim]")
    console.print("  " + "  [dim]·[/dim]  ".join(parts))

    if report_dest:
        console.print(f"  [dim]Report → {report_dest}[/dim]")
    console.print()


@cli.command()
@click.option(
    "-e",
    "--entity",
    type=str,
    default="_all",
    show_default=True,
    help="Entity to validate (_all for every entity).",
)
@click.option(
    "-m",
    "--method",
    type=str,
    default="_all",
    show_default=True,
    help="Method to validate (_all for every saved method).",
)
@click.option("--prune", is_flag=True, help="Remove tests that fail validation.")
@click.option("--no-async", "no_async", is_flag=True, help="Run validation synchronously.")
@click.option(
    "--async-limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum number of validations to run concurrently.",
)
@click.option("--cleanup", is_flag=True, help="Clean up created entities after validation.")
@click.option(
    "--report-path",
    type=click.Path(),
    default=None,
    help="Override report output path (default: ~/rizza/validation/<product>-DDMMMYY.yaml).",
)
@click.option(
    "--report-format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    show_default=True,
    help="Report file format.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging level.")
@click.option(
    "--from-version",
    "from_version",
    type=str,
    default=None,
    help="Validate using tests from version X.Y[.Z] against the current server.",
)
@click.pass_context
def validate(
    ctx,
    entity,
    method,
    prune,
    no_async,
    async_limit,
    cleanup,
    report_path,
    report_format,
    debug,
    from_version,
):
    """Re-run saved tests to confirm they still pass. Optionally prune failures."""
    conf = ctx.obj
    run_async = not no_async

    if from_version and prune:
        click.echo(
            "Cannot use --prune with --from-version (cross-version is read-only).", err=True
        )
        sys.exit(1)

    data_dir = None
    if from_version:
        data_dir = conf.genetic_tests_dir_for_version(from_version)
        if not data_dir.exists():
            click.echo(f"No test data found for version {from_version!r} at {data_dir}", err=True)
            sys.exit(1)

    conf.init_logger(
        path=conf.base_dir.joinpath("logs/validate.log"),
        level="debug" if debug else None,
    )
    conf.init_connection()

    total = prune_helper.count_pending_tests(conf, entity, method, data_dir=data_dir)

    progress = genetic_tester._make_progress()
    conf._progress = progress
    conf._validate_task = progress.add_task(
        "[bold]Validating[/bold]", total=total if total > 0 else 1
    )

    with progress:
        if run_async and entity == "_all":
            results = prune_helper.async_validate_tests(
                conf,
                entity=entity,
                method=method,
                prune=prune,
                async_limit=async_limit,
                data_dir=data_dir,
            )
        else:
            results = prune_helper.validate_tests(
                conf, entity=entity, method=method, prune=prune, data_dir=data_dir
            )

    conf._progress = None
    conf._validate_task = None

    report_dest = None
    if results:
        report_dest = _write_validation_report(
            conf, results, report_path, report_format, entity, method
        )

    _print_validation_summary(results, prune, report_dest)

    if from_version and results:
        passed = [r for r in results if r["passed"]]
        if passed and click.confirm(
            f"\nCopy {len(passed)} passing test(s) to {conf.product_slug}?"
        ):
            _copy_passing_tests(conf, results, from_version)

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
@click.argument("chunk", required=False, type=click.Choice(["rizza", "genetics", "connection"]))
@click.option("--force", is_flag=True, help="Overwrite existing config files.")
@click.pass_context
def config_init(ctx, chunk, force):
    """Initialize config files from bundled examples.

    Optionally pass a CHUNK name (rizza, genetics, connection) to reinitialize
    only that file, leaving the others untouched.
    """
    conf = ctx.obj
    result = conf.init_config(force=force, chunk=chunk)
    if result["copied"]:
        click.echo(f"Created: {', '.join(result['copied'])}")
    if result["skipped"]:
        skipped = ", ".join(result["skipped"])
        click.echo(f"Skipped (already exist): {skipped} (use --force to overwrite)")


@cli.command(name="list")
@click.argument(
    "subject", type=click.Choice(["entities", "methods", "fields", "args", "input-methods"])
)
@click.option("-e", "--entity", type=str, help="The name of the entity you want to filter by.")
@click.option("-m", "--method", type=str, help="The name of the method you want to filter by.")
@click.option("--new", "show_new", is_flag=True, help="Show only methods without a passing test.")
@click.option(
    "--explored",
    "show_explored",
    is_flag=True,
    help="Show only methods that already have a passing test.",
)
@click.pass_context
def list_cmd(ctx, subject, entity, method, show_new, show_explored):
    """List out information about entities and inputs."""
    conf = ctx.obj
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
    _list_subject(conf, subject, entity, method, show_new, show_explored)


def _list_subject(conf, subject, entity_name, method_name, show_new=False, show_explored=False):
    """Helper function to handle listing logic for different subjects."""
    if subject == "entities":
        _list_entities()
    elif subject == "input-methods":
        _list_input_methods()
    else:
        _list_entity_details(conf, subject, entity_name, method_name, show_new, show_explored)


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


def _list_entity_details(conf, subject, entity_name, method_name, show_new, show_explored):
    """List details (methods, fields, args) for a specific entity."""
    pulled_entities = EntityTester.pull_entities()
    if entity_name not in pulled_entities:
        click.echo(f"Entity '{entity_name}' not found.", err=True)
        return

    entity_data = pulled_entities[entity_name]
    if subject == "methods":
        _list_entity_methods(conf, entity_data, entity_name, show_new, show_explored)
    elif subject == "fields":
        _list_entity_fields(entity_data, entity_name)
    elif subject == "args":
        _list_method_args(entity_data, entity_name, method_name)
    else:
        click.echo(f"Unknown subject '{subject}' for entity listing.", err=True)


def _list_entity_methods(conf, entity_data, entity_name, show_new, show_explored):
    """List methods for a given entity, with optional new/explored filtering."""
    if show_new or show_explored:
        from rizza.helpers.method_resolver import get_explored_methods, get_new_methods

        if show_new:
            methods_dict = get_new_methods(conf, entity_name, entity_data)
            label = "untested"
        else:
            methods_dict = get_explored_methods(conf, entity_name, entity_data)
            label = "explored"
        methods_list = list(methods_dict.keys())
        if methods_list:
            for item in methods_list:
                rprint(item)
        else:
            click.echo(f"No {label} methods found for entity '{entity_name}'.")
    else:
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


@cli.group()
@click.pass_context
def knowledge(ctx):
    """Inspect rizza's saved genetic tests and agentic policy knowledge base."""
    pass


@knowledge.command(name="genetic")
@click.option(
    "--version",
    "version",
    default=None,
    help="Show tests for a specific version (default: config version).",
)
@click.pass_context
def knowledge_genetic(ctx, version):
    """Show saved genetic test results, grouped by entity."""
    import yaml as _yaml

    conf = ctx.obj
    data_dir = conf.genetic_tests_dir_for_version(version) if version else conf.genetic_tests_dir
    if not data_dir.exists():
        click.echo("No saved genetic tests found.")
        return
    yaml_files = sorted(data_dir.glob("*.yaml"))
    if not yaml_files:
        click.echo("No saved genetic tests found.")
        return
    rprint(
        f"\n[bold]Saved Genetic Tests[/bold]  [dim]({data_dir})[/dim]"
        f"  [dim][{conf.product_slug}][/dim]\n"
    )
    for yaml_file in yaml_files:
        tests = _yaml.safe_load(yaml_file.read_text()) or {}
        if not tests:
            continue
        entity_name = yaml_file.stem
        rprint(f"[bold cyan]{entity_name}[/bold cyan]")
        for test_name, test_data in tests.items():
            arg_dict = test_data.get("arg_dict", {})
            rprint(f"  [green]{test_name}[/green]")
            for k, v in arg_dict.items():
                rprint(f"    [dim]{k}={v}[/dim]")
        rprint("")


def _q_value_lines(labels, q_values):
    """Build sorted Q-value display lines with softmax percentages."""
    import math

    pairs = list(zip(labels, q_values, strict=False))
    max_q = max(q_values) if q_values else 0.0
    exp_vals = [math.exp(v - max_q) for v in q_values]
    exp_sum = sum(exp_vals)
    pcts = [e / exp_sum * 100.0 for e in exp_vals]
    combined = [(lbl, qv, pct) for (lbl, qv), pct in zip(pairs, pcts, strict=False)]
    combined.sort(key=lambda x: x[1], reverse=True)
    max_label_len = max(len(lbl) for lbl, _, _ in combined) if combined else 0
    lines = []
    for lbl, qv, pct in combined:
        lines.append(f"    {lbl:<{max_label_len}}  {qv:+.2f}  [dim]({pct:.1f}%)[/dim]")
    return lines


def _nn_q_values_from_state_dict(sd, torch):
    """Reconstruct an MLP from a state_dict and run a zero vector to get baseline Q-values."""
    from torch import nn

    weight_keys = [k for k in sd if k.endswith(".weight") and len(sd[k].shape) == 2]
    bias_keys = [k for k in sd if k.endswith(".bias") and len(sd[k].shape) == 1]
    weight_keys.sort()
    bias_keys.sort()
    if not weight_keys:
        return None
    layers = []
    for i, wk in enumerate(weight_keys):
        out_dim, in_dim = sd[wk].shape
        linear = nn.Linear(in_dim, out_dim)
        linear.weight.data = sd[wk]
        bk = bias_keys[i] if i < len(bias_keys) else None
        if bk:
            linear.bias.data = sd[bk]
        layers.append(linear)
        if i < len(weight_keys) - 1:
            layers.append(nn.ReLU())
    net = nn.Sequential(*layers)
    net.eval()
    input_dim = sd[weight_keys[0]].shape[1]
    with torch.no_grad():
        return net(torch.zeros(1, input_dim)).squeeze().tolist()


def _knowledge_show_qtable(product, interface, data, top, action_labels):
    """Display Q-table (Tier 1) policy statistics."""
    import ast as _ast

    epsilon = data.get("epsilon", 0.0)
    raw_table = data.get("q_table", {})
    state_count = len(raw_table)
    rprint(
        f"[bold cyan]{product}[/bold cyan] / [cyan]{interface}[/cyan]"
        f"  ·  [dim]Q-Table (Tier 1)[/dim]"
    )
    rprint(
        f"  Epsilon:        [yellow]{epsilon:.3f}[/yellow]"
        f"  [dim]({epsilon * 100:.1f}% exploration remaining)[/dim]"
    )
    rprint(f"  States learned: [yellow]{state_count}[/yellow]")
    if state_count:
        all_q = list(raw_table.values())
        n_actions = len(all_q[0]) if all_q else 0
        if n_actions:
            mean_q = [sum(q[i] for q in all_q) / len(all_q) for i in range(n_actions)]
            labels = action_labels[:n_actions]
            rprint(f"  Q-values:      [dim](mean across {state_count} states)[/dim]")
            for line in _q_value_lines(labels, mean_q):
                rprint(line)
    if state_count and top > 0:
        decoded = []
        for k_str, q_vals in raw_table.items():
            try:
                key = _ast.literal_eval(k_str)
                decoded.append((key, q_vals))
            except Exception:
                pass
        decoded.sort(key=lambda x: max(x[1]), reverse=True)
        rprint(f"\n  [dim]Top {min(top, len(decoded))} states by best Q-value:[/dim]")
        for key, q_vals in decoded[:top]:
            status, err_cls, text = key[0], key[1], key[2]
            label = f'{status} · {err_cls} · "{text[:40]}{"..." if len(text) > 40 else ""}"'
            rprint(f"    [dim]{label}[/dim]")
            best_idx = q_vals.index(max(q_vals))
            parts_row = []
            for i, (lbl, val) in enumerate(zip(action_labels, q_vals, strict=False)):
                fmt = (
                    f"[bold green]{lbl} {val:+.2f} ★[/bold green]"
                    if i == best_idx
                    else f"{lbl} {val:+.2f}"
                )
                parts_row.append(fmt)
            rprint(f"      {'   '.join(parts_row)}")
    rprint("")


def _knowledge_show_gen_recommender(product, interface, policy_file):
    """Display generator recommender (NLP) statistics."""
    rprint(
        f"[bold cyan]{product}[/bold cyan] / [cyan]{interface}[/cyan]"
        f"  ·  [dim]Generator Recommender (NLP)[/dim]"
    )
    try:
        import torch as _torch

        checkpoint = _torch.load(policy_file, map_location="cpu", weights_only=False)
        epsilon = checkpoint.get("epsilon", 0.0)
        gen_names = checkpoint.get("generator_names", [])
        sd = checkpoint.get("state_dict", {})
        weight_shapes = [list(v.shape) for v in sd.values() if len(v.shape) == 2]
        dims = (
            str(weight_shapes[0][1]) + " → " + " → ".join(str(s[0]) for s in weight_shapes)
            if weight_shapes
            else "unknown"
        )
        rprint(
            f"  Epsilon:       [yellow]{epsilon:.3f}[/yellow]"
            f"  [dim]({epsilon * 100:.1f}% exploration remaining)[/dim]"
        )
        rprint(f"  Architecture:  [dim]{dims}[/dim]")
        rprint(f"  Generators:    [yellow]{len(gen_names)}[/yellow] known")
        q_vals = _nn_q_values_from_state_dict(sd, _torch)
        if q_vals and gen_names and len(q_vals) == len(gen_names):
            rprint("  Q-values:      [dim](baseline output scores)[/dim]")
            for line in _q_value_lines(gen_names, q_vals):
                rprint(line)
    except ImportError:
        rprint("  [dim](torch not installed — install rizza[agentic] to read weights)[/dim]")
    except Exception as e:
        rprint(f"  [red]Error reading weights: {e}[/red]")
    rprint("")


def _knowledge_show_dqn(product, interface, policy_file):
    """Display DQN action policy statistics."""
    _action_labels = ["SWAP", "ADD", "DROP", "NOOP", "TARGETED_SWAP"]
    rprint(
        f"[bold cyan]{product}[/bold cyan] / [cyan]{interface}[/cyan]"
        f"  ·  [dim]Action Policy (deep RL)[/dim]"
    )
    try:
        import torch as _torch

        checkpoint = _torch.load(policy_file, map_location="cpu", weights_only=True)
        epsilon = checkpoint.get("epsilon", 0.0)
        sd = checkpoint.get("state_dict", {})
        shapes = [list(v.shape) for v in sd.values() if len(v.shape) == 2]
        dims = (
            " → ".join(str(s[1]) for s in shapes) + f" → {shapes[-1][0]}" if shapes else "unknown"
        )
        n_actions = shapes[-1][0] if shapes else len(_action_labels)
        known_actions = _action_labels[:n_actions]
        rprint(
            f"  Epsilon:       [yellow]{epsilon:.3f}[/yellow]"
            f"  [dim]({epsilon * 100:.1f}% exploration remaining)[/dim]"
        )
        rprint(f"  Architecture:  [dim]{dims}[/dim]")
        rprint(
            f"  Actions:       [yellow]{n_actions}[/yellow] known"
            f"  [dim]({', '.join(known_actions)})[/dim]"
        )
        q_vals = _nn_q_values_from_state_dict(sd, _torch)
        if q_vals and len(q_vals) == n_actions:
            rprint("  Q-values:      [dim](baseline output scores)[/dim]")
            for line in _q_value_lines(known_actions, q_vals):
                rprint(line)
    except ImportError:
        rprint("  [dim](torch not installed — install rizza[agentic] to read weights)[/dim]")
    except Exception as e:
        rprint(f"  [red]Error reading weights: {e}[/red]")
    rprint("")


@knowledge.command(name="agentic")
@click.option(
    "--top",
    type=int,
    default=5,
    show_default=True,
    help="Number of top learned states to display (Q-table only).",
)
@click.option(
    "--version",
    "version",
    default=None,
    help="Show policies for a specific version (default: all versions).",
)
@click.pass_context
def knowledge_agentic(ctx, top, version):
    """Show agentic RL policy stats, grouped by product and interface."""
    import json as _json

    conf = ctx.obj
    agentic_dir = conf.base_dir / "data" / "agentic"
    if not agentic_dir.exists():
        click.echo("No agentic knowledge base found.")
        return

    from rizza.helpers.config import _version_minor

    version_filter = _version_minor(version) if version else None

    policy_files = (
        list(agentic_dir.rglob("qtable.json"))
        + list(agentic_dir.rglob("dqn.pt"))
        + list(agentic_dir.rglob("gen_recommender.pt"))
    )
    if not policy_files:
        click.echo("No agentic knowledge base found.")
        return

    if version_filter:
        policy_files = [
            pf
            for pf in policy_files
            if pf.relative_to(agentic_dir).parts[0].endswith(f"-{version_filter}")
        ]
        if not policy_files:
            click.echo(f"No agentic policies found for version {version!r}.")
            return

    action_labels = ["SWAP", "ADD", "DROP", "NOOP", "TARGETED_SWAP"]
    rprint(f"\n[bold]Agentic Knowledge Base[/bold]  [dim]({agentic_dir})[/dim]\n")

    for policy_file in sorted(policy_files):
        rel_parts = policy_file.relative_to(agentic_dir).parts
        product_slug = rel_parts[0] if len(rel_parts) > 2 else "unknown"
        interface = rel_parts[1] if len(rel_parts) > 2 else "unknown"

        if policy_file.suffix == ".json":
            try:
                data = _json.loads(policy_file.read_text())
            except Exception as e:
                rprint(f"  [red]Error reading {policy_file.name}: {e}[/red]")
                continue
            _knowledge_show_qtable(product_slug, interface, data, top, action_labels)

        elif policy_file.name == "gen_recommender.pt":
            _knowledge_show_gen_recommender(product_slug, interface, policy_file)

        elif policy_file.suffix == ".pt":
            _knowledge_show_dqn(product_slug, interface, policy_file)


@knowledge.command(name="products")
@click.pass_context
def knowledge_products(ctx):
    """List all saved products and versions, highlighting the active one."""
    from rich.tree import Tree

    conf = ctx.obj
    # {product_name: {version: set(interfaces)}}
    products = {}

    genetic_base = conf.base_dir / "data" / "genetic_tests"
    agentic_base = conf.base_dir / "data" / "agentic"

    for base in [genetic_base, agentic_base]:
        if not base.exists():
            continue
        for slug_dir in sorted(base.iterdir()):
            if not slug_dir.is_dir():
                continue
            name, version = _parse_product_slug(slug_dir.name)
            if not name:
                continue
            entry = products.setdefault(name, {}).setdefault(version, set())
            for iface_dir in slug_dir.iterdir():
                if iface_dir.is_dir():
                    entry.add(iface_dir.name)

    if not products:
        click.echo("No saved product data found.")
        return

    active_name = getattr(conf.rizza, "product_name", "satellite")
    active_version = conf.product_version_minor

    tree = Tree("[bold]Saved Products[/bold]")
    for name in sorted(products):
        product_branch = tree.add(f"[bold cyan]{name}[/bold cyan]")
        for version in sorted(products[name], key=_version_sort_key):
            interfaces = sorted(products[name][version])
            iface_str = ", ".join(interfaces) if interfaces else "none"
            is_active = name == active_name and version == active_version
            if is_active:
                product_branch.add(
                    f"[bold green]{version}[/bold green] [dim]({iface_str})[/dim]"
                    f"  [green]<- active[/green]"
                )
            else:
                product_branch.add(f"{version} [dim]({iface_str})[/dim]")

    console.print()
    console.print(tree)
    console.print()


def _parse_product_slug(slug):
    """Parse 'satellite-6.12' → ('satellite', '6.12'). Returns (None, None) on failure."""
    idx = slug.rfind("-")
    if idx <= 0:
        return None, None
    name = slug[:idx]
    version = slug[idx + 1 :]
    return name, version


def _version_sort_key(version):
    """Sort versions numerically where possible, with 'stream' last."""
    if version == "stream":
        return (999, 999)
    try:
        parts = version.split(".")
        return tuple(int(p) for p in parts)
    except ValueError:
        return (998,)


@cli.group()
@click.pass_context
def permutations(ctx):
    """View permutation telemetry from GA exploration runs."""
    pass


def _open_telemetry_store(conf, version=None):
    """Open a PermutationStore for the given config and optional version override."""
    from rizza.helpers.telemetry import PermutationStore

    db_dir = conf.telemetry_dir_for_version(version) if version else conf.telemetry_dir
    db_path = db_dir / "permutations.db"
    if not db_path.exists():
        return None
    return PermutationStore(db_path=db_path)


@permutations.command(name="entity")
@click.option("-e", "--entity", type=str, default=None, help="Filter to a specific entity.")
@click.option("--version", type=str, default=None, help="Show telemetry for a specific version.")
@click.pass_context
def permutations_entity(ctx, entity, version):
    """Per-method summary with pass/fail totals."""
    conf = ctx.obj
    store = _open_telemetry_store(conf, version)
    if store is None:
        click.echo("No telemetry data found. Run `rizza explore` first.")
        return
    try:
        rows = store.query_method_summary(entity)
        if not rows:
            click.echo(
                f"No telemetry data for entity {entity!r}."
                if entity
                else "No telemetry data found."
            )
            return
        coverage = store.compute_coverage(entity)
        if entity:
            _render_entity_detail(rows, entity, coverage)
        else:
            _render_method_summary(rows, coverage)
    finally:
        store.close()


@permutations.command(name="method")
@click.option("-e", "--entity", type=str, required=True, help="Entity name.")
@click.option("-m", "--method", type=str, required=True, help="Method name.")
@click.option("--version", type=str, default=None, help="Show telemetry for a specific version.")
@click.pass_context
def permutations_method(ctx, entity, method, version):
    """Hierarchical parameter triage tree for a specific method."""
    conf = ctx.obj
    store = _open_telemetry_store(conf, version)
    if store is None:
        click.echo("No telemetry data found. Run `rizza explore` first.")
        return
    try:
        method_name = f"{entity}.{method}"
        tree_data = store.query_method_tree(method_name)
        if not tree_data:
            click.echo(f"No permutation data for {method_name}.")
            return
        _render_method_tree(tree_data, method_name)
    finally:
        store.close()


_ILLION_UNITS = ["", "un", "duo", "tre", "quattuor", "quin", "sex", "septen", "octo", "novem"]
_ILLION_TENS = [
    "",
    "deci",
    "viginti",
    "triginta",
    "quadraginta",
    "quinquaginta",
    "sexaginta",
    "septuaginta",
    "octoginta",
    "nonaginta",
]
_ILLION_HUNDREDS = [
    "",
    "centi",
    "ducenti",
    "trecenti",
    "quadringenti",
    "quingenti",
    "sescenti",
    "septingenti",
    "octingenti",
    "nongenti",
]
_ILLION_SPECIAL = {
    1: "million",
    2: "billion",
    3: "trillion",
    4: "quadrillion",
    5: "quintillion",
    6: "sextillion",
    7: "septillion",
    8: "octillion",
    9: "nonillion",
}


def _illion_name(n):
    """Return the short-scale name for 10**(3*n+3), e.g. 1 -> million, 100 -> centillion."""
    if n in _ILLION_SPECIAL:
        return _ILLION_SPECIAL[n]
    hundreds, rem = divmod(n, 100)
    tens, units = divmod(rem, 10)
    prefix = _ILLION_UNITS[units] + _ILLION_TENS[tens] + _ILLION_HUNDREDS[hundreds]
    if prefix and prefix[-1] in "aeiou":
        prefix = prefix[:-1]
    return f"{prefix}illion"


def _format_permutation_count(n):
    """Format a permutation count for display: exact with commas if small, else a scale name."""
    n = int(n)
    if n < 1_000_000:
        return f"{n:,}"

    digits = str(n)
    digit_count = len(digits)
    groups = (digit_count + 2) // 3
    idx = groups - 2
    lead_len = digit_count - 3 * (groups - 1)
    lead = digits[:lead_len]
    frac = digits[lead_len : lead_len + 2]

    if idx > 100:
        mantissa = f"{digits[0]}.{digits[1:3]}".rstrip("0").rstrip(".")
        return f"{mantissa}e+{digit_count - 1}"

    value = lead if frac.strip("0") == "" else f"{lead}.{frac}"
    name = "thousand" if idx == 0 else _illion_name(idx)
    return f"{value} {name}"


def _render_method_summary(rows, coverage):
    """Render entity-level summary table aggregated across methods."""
    from collections import OrderedDict

    from rich.table import Table

    entities = OrderedDict()
    for r in rows:
        name = r["name"]
        entity = name.split(".", 1)[0] if "." in name else name
        acc = entities.setdefault(entity, {"perms": 0, "passes": 0, "fails": 0})
        acc["perms"] += r["total_permutations"] or 0
        acc["passes"] += r["total_passes"] or 0
        acc["fails"] += r["total_fails"] or 0

    table = Table(title="Permutation Summary", show_lines=False)
    table.add_column("Entity", style="bold cyan")
    table.add_column("Perms", justify="right")
    table.add_column("Passes", justify="right", style="green")
    table.add_column("Fails", justify="right", style="red")
    table.add_column("Pass Rate", justify="right")

    for entity, acc in entities.items():
        total = acc["passes"] + acc["fails"]
        rate = acc["passes"] * 100.0 / max(total, 1)
        if rate >= 10:
            rate_style = "bold green"
        elif rate >= 1:
            rate_style = "yellow"
        else:
            rate_style = "red"

        table.add_row(
            entity,
            str(acc["perms"]),
            str(acc["passes"]),
            str(acc["fails"]),
            f"[{rate_style}]{rate:.1f}%[/{rate_style}]",
        )

    console.print()
    console.print(table)
    tested, possible = coverage
    console.print(
        f"  [dim]Tested {_format_permutation_count(tested)} / "
        f"{_format_permutation_count(possible)} permutations[/dim]"
    )
    console.print()


def _render_entity_detail(rows, entity_name, coverage):
    """Render per-method breakdown for a single entity."""
    from rich.table import Table

    table = Table(title=f"{entity_name} — Method Breakdown", show_lines=False)
    table.add_column("Method", style="bold")
    table.add_column("Perms", justify="right")
    table.add_column("Passes", justify="right", style="green")
    table.add_column("Fails", justify="right", style="red")
    table.add_column("Pass Rate", justify="right")

    for r in rows:
        name = r["name"]
        method = name.split(".", 1)[1] if "." in name else name

        passes = r["total_passes"] or 0
        fails = r["total_fails"] or 0
        total = passes + fails
        rate = passes * 100.0 / max(total, 1)
        if rate >= 10:
            rate_style = "bold green"
        elif rate >= 1:
            rate_style = "yellow"
        else:
            rate_style = "red"

        table.add_row(
            method,
            str(r["total_permutations"] or 0),
            str(passes),
            str(fails),
            f"[{rate_style}]{rate:.1f}%[/{rate_style}]",
        )

    console.print()
    console.print(table)
    tested, possible = coverage
    console.print(
        f"  [dim]Tested {_format_permutation_count(tested)} / "
        f"{_format_permutation_count(possible)} permutations[/dim]"
    )
    console.print()


def _render_method_tree(tree_data, method_name):
    """Render hierarchical parameter triage tree with range and volatility."""
    from collections import defaultdict

    from rich.tree import Tree

    # Build nested structure: param -> status -> [{generator, pass_count, fail_count}]
    structure = defaultdict(lambda: defaultdict(list))
    seen = set()
    for r in tree_data:
        key = (r["param_name"], r["status"], r["generator_name"])
        if key in seen:
            continue
        seen.add(key)
        structure[r["param_name"]][r["status"]].append(
            {
                "generator": r["generator_name"],
                "pass_count": r["pass_count"],
                "fail_count": r["fail_count"],
            }
        )

    tree = Tree(f"[bold]Method: {method_name}[/bold]")

    for param_name in sorted(structure):
        param_branch = tree.add(f"[bold cyan]Parameter: {param_name}[/bold cyan]")

        for status in sorted(structure[param_name]):
            generators = structure[param_name][status]
            rates = []
            for g in generators:
                total = g["pass_count"] + g["fail_count"]
                rates.append(g["pass_count"] * 100.0 / max(total, 1))

            spread = max(rates) - min(rates) if len(rates) >= 2 else 0.0
            status_branch = param_branch.add(f"Status: {status} [dim](range: {spread:.1f}%)[/dim]")

            for g in generators:
                total = g["pass_count"] + g["fail_count"]
                p = g["pass_count"] / max(total, 1)
                volatility = p * (1.0 - p)
                rate = p * 100.0

                if rate >= 50:
                    rate_style = "green"
                elif rate > 0:
                    rate_style = "yellow"
                else:
                    rate_style = "red"

                status_branch.add(
                    f"[{rate_style}]{g['generator']}[/{rate_style}]"
                    f" — {rate:.1f}% pass"
                    f" ({total} hits,"
                    f" volatility: {volatility:.3f})"
                )

    console.print()
    console.print(tree)
    console.print()


_interrupted = False


def _note_sigint(signum, frame):
    """Record that a SIGINT arrived, then fall through to the usual KeyboardInterrupt."""
    global _interrupted
    _interrupted = True
    raise KeyboardInterrupt


def _exit_after_interrupt():
    """Terminate immediately after a Ctrl-C, skipping the normal shutdown sequence.

    A long-running explore/validate can leave a non-daemon executor thread blocked
    in a synchronous HTTP call with no way to cancel it. Waiting on the normal
    interpreter shutdown to join that thread can hang, or force the user into
    repeated Ctrl-C that crashes the process. Everything that matters (checkpoints,
    telemetry) is already flushed via `finally` blocks by the time we get here, so
    it's safe to skip the rest of the shutdown sequence and exit now.
    """
    console.print("\n[yellow]Interrupted by user — exiting.[/yellow]")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(130)


def main():
    """Entry point for both `python -m rizza` and the installed `rizza` console script."""
    signal.signal(signal.SIGINT, _note_sigint)
    try:
        cli(obj=None)
    except KeyboardInterrupt:
        # In case a SIGINT lands outside the try/except that click itself wraps
        # around command execution (e.g. during its shell-completion preamble).
        _exit_after_interrupt()
    except SystemExit:
        # click (via rich_click) already turns KeyboardInterrupt into its own
        # "Aborted!" message + sys.exit(1); catch that here so we can still
        # short-circuit the shutdown sequence when _note_sigint flagged it.
        if _interrupted:
            _exit_after_interrupt()
        raise
    except Exception as err:
        logger.exception(f"An unexpected error occurred: {err}")
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
