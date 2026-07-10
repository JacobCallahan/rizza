"""A module that provides utilities to test entities via genetic algorithms."""

import asyncio
import contextvars
import inspect
import logging
import random

import attr
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
import yaml

from rizza import entity_tester
from rizza.helpers import genetics
from rizza.helpers.logging import console
from rizza.helpers.misc import dict_search

logger = logging.getLogger(__name__)

_replay_mode = contextvars.ContextVar("_replay_mode", default=False)


def _make_progress():
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}", markup=True),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def _safe_str(v):
    """Return v as-is if it's a JSON-safe scalar/container, else convert to str."""
    if isinstance(v, str | int | float | bool | type(None) | dict | list):
        return v
    return str(v)


# Cached result of the agentic-learner import check — avoids repeated warnings.
_AGENTIC_AVAILABLE = None


def _entity_from_param_name(param_name, known_entity_names_lower):
    """If param ends in _id/_ids and its base matches a known entity, return that entity's name."""
    name = param_name.lower()
    if name.endswith("_ids"):
        base = name[:-4]
    elif name.endswith("_id"):
        base = name[:-3]
    else:
        return None
    return known_entity_names_lower.get(base)


def run_all_entities(**kwargs):
    """Iterate through all known entities and attempt to test them.

    :param method: "_new", "_all", or a specific method name.
    """
    from rizza.helpers.method_resolver import resolve_methods

    debug = kwargs.pop("debug")
    async_mode = kwargs.pop("async_mode")
    method_mode = kwargs.pop("method", "_new")
    seek_bad = kwargs.get("seek_bad", False)
    if not async_mode:
        kwargs.pop("max_running", None)

    pulled_entities = entity_tester.EntityTester.pull_entities()
    if not pulled_entities:
        logger.warning("Genetic tests: No entities found to test.")
        return

    entity_list = list(pulled_entities)
    from_entity = kwargs.pop("from_entity")
    from_method = kwargs.pop("from_method", None)
    if from_entity:
        try:
            entity_list = entity_list[entity_list.index(from_entity) :]
        except ValueError:
            logger.warning(f"Entity {from_entity!r} not found — starting from the beginning.")
            from_method = None
    config = kwargs["config"]

    progress = _make_progress()
    config._progress = progress
    entity_task = progress.add_task("[bold]Entities[/bold]", total=len(entity_list))

    explored = 0
    try:
        with progress:
            for entity_name in entity_list:
                entity_cls = pulled_entities[entity_name]
                progress.update(entity_task, description=f"[bold]Entity:[/bold] {entity_name}")
                methods = resolve_methods(config, entity_name, entity_cls, method_mode, seek_bad)
                if not methods:
                    progress.console.print(
                        f"[dim]Skipping {entity_name}: no methods to explore[/dim]"
                    )
                    progress.advance(entity_task)
                    continue
                method_list = list(methods)
                if from_method and entity_name == entity_list[0]:
                    try:
                        method_list = method_list[method_list.index(from_method) :]
                    except ValueError:
                        logger.warning(
                            f"Method {from_method!r} not found on {entity_name} — "
                            "starting from the first method."
                        )
                for method_name in method_list:
                    config.save_checkpoint(entity_name, method_name)
                    kwargs["entity"] = entity_name
                    kwargs["method"] = method_name
                    try:
                        if async_mode:
                            gtester = AsyncGeneticEntityTester(**kwargs)
                        else:
                            gtester = GeneticEntityTester(**kwargs)
                    except Exception as err:
                        progress.console.print(
                            f"[yellow]Warning:[/yellow] Unable to create a tester for "
                            f"{entity_name}.{method_name}: {err}"
                        )
                        continue
                    config.init_logger(
                        path=config.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
                        level="debug" if debug else None,
                    )
                    gtester.run()
                    explored += 1
                progress.advance(entity_task)
    finally:
        config._progress = None

    if explored == 0:
        logger.info("All methods already explored. Nothing new to run.")
    else:
        logger.info(f"Finished testing all entities! ({explored} method runs)")


def run_failed_entities(failed_map, **kwargs):
    """Re-explore entity/method pairs from a last_failed.json map.

    :param failed_map: dict of {entity_name: [method_name, ...]} from last_failed.json.
    """
    debug = kwargs.pop("debug", False)
    async_mode = kwargs.pop("async_mode", True)
    if not async_mode:
        kwargs.pop("max_running", None)
    kwargs.pop("method", None)
    kwargs.pop("from_entity", None)

    pulled_entities = entity_tester.EntityTester.pull_entities()
    config = kwargs["config"]

    entity_list = [
        (name, methods) for name, methods in failed_map.items() if name in pulled_entities
    ]
    if not entity_list:
        logger.warning("No matching entities found in last_failed.json.")
        return

    progress = _make_progress()
    config._progress = progress
    entity_task = progress.add_task("[bold]Entities (failed)[/bold]", total=len(entity_list))

    explored = 0
    try:
        with progress:
            for entity_name, methods in entity_list:
                entity_cls = pulled_entities[entity_name]
                progress.update(entity_task, description=f"[bold]Entity:[/bold] {entity_name}")
                if not methods:
                    progress.console.print(
                        f"[dim]Skipping {entity_name}: no failed methods listed[/dim]"
                    )
                    progress.advance(entity_task)
                    continue
                for method_name in methods:
                    if not entity_tester.EntityTester.pull_methods(entity_cls).get(method_name):
                        progress.console.print(
                            f"[yellow]Warning:[/yellow] Method {method_name!r} not found on "
                            f"{entity_name}, skipping"
                        )
                        continue
                    kwargs["entity"] = entity_name
                    kwargs["method"] = method_name
                    try:
                        if async_mode:
                            gtester = AsyncGeneticEntityTester(**kwargs)
                        else:
                            gtester = GeneticEntityTester(**kwargs)
                    except Exception as err:
                        progress.console.print(
                            f"[yellow]Warning:[/yellow] Unable to create tester for "
                            f"{entity_name}.{method_name}: {err}"
                        )
                        continue
                    config.init_logger(
                        path=config.base_dir.joinpath(f"logs/genetic/{gtester.test_name}.log"),
                        level="debug" if debug else None,
                    )
                    gtester.run()
                    explored += 1
                progress.advance(entity_task)
    finally:
        config._progress = None

    if explored == 0:
        logger.info("No failed methods could be re-explored.")
    else:
        logger.info(f"Finished re-exploring failed entities! ({explored} method runs)")


@attr.s()
class GeneticEntityTester:
    """Class that handles all aspects of genetic algorithm-based testing.

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
        """Perform more complex class initialization."""
        self.test_name = "{} {} {}".format(
            self.entity, self.method, "negative" if self.seek_bad else "positive"
        )
        if not self.population_count:
            self.population_count = self.config.rizza.genetics.population_count
        if not self.max_generations:
            self.max_generations = self.config.rizza.genetics.max_generations

        # Apply CLI overrides to config
        if self.max_recursive_generations:
            self.config.rizza.genetics.max_recursive_generations = self.max_recursive_generations
        if self.disable_dependencies:
            self.config.rizza.genetics.allow_dependencies = False
        if self.disable_recursion:
            self.config.rizza.genetics.allow_recursion = False
        if self.max_recursive_depth:
            self.config.rizza.genetics.max_recursive_depth = self.max_recursive_depth

        # Resolve entity and method from apix module
        pulled_entities = entity_tester.EntityTester.pull_entities()
        self._entity_cls = pulled_entities.get(self.entity)
        if self._entity_cls:
            methods = entity_tester.EntityTester.pull_methods(self._entity_cls)
            self._method = methods.get(self.method)
            init_sig = inspect.signature(self._entity_cls.__init__)
            self._init_params = [p for p in init_sig.parameters if p != "self"]
            init_required = {
                name
                for name, param in init_sig.parameters.items()
                if name != "self" and param.default is inspect.Parameter.empty
            }
        else:
            logger.warning(f"GeneticTester: Entity '{self.entity}' not found in apix module.")
            self._entity_cls = None
            self._method = None
            self._init_params = []
            init_required = set()

        method_required = set()
        if self._method:
            method_sig = inspect.signature(self._method)
            method_required = {
                name
                for name, param in method_sig.parameters.items()
                if name != "self" and param.default is inspect.Parameter.empty
            }

        # Build type_pools: {param_name: [compatible_input_names]}
        self._type_pools = self._build_type_pools()

        # All available param names for variable-length gene operators
        method_params = (
            entity_tester.EntityTester.pull_args(self._method) or [] if self._method else []
        )
        self._available_params = list(dict.fromkeys(self._init_params + method_params))

        # Required params are always seeded and protected from DROP
        self._required_params = init_required | method_required

        agentic_cfg = getattr(self.config.rizza.genetics, "agentic", None)
        if agentic_cfg and getattr(agentic_cfg, "enabled", False):
            global _AGENTIC_AVAILABLE
            if _AGENTIC_AVAILABLE is None:
                try:
                    from rizza.agentic_tester import AgenticPayloadLearner as _chk  # noqa: F401

                    _AGENTIC_AVAILABLE = True
                except (ImportError, Exception) as err:
                    logger.warning(f"Agentic learner disabled: {err}")
                    _AGENTIC_AVAILABLE = False
            if _AGENTIC_AVAILABLE:
                try:
                    from pathlib import Path as _Path

                    from rizza.agentic_tester import AgenticPayloadLearner

                    _apix_path = getattr(self.config.rizza, "apix_lib_path", "") or ""
                    _product = _Path(_apix_path).stem or "default"
                    self._agentic_learner = AgenticPayloadLearner(
                        config=agentic_cfg,
                        judge_fn=self._judge,
                        genes_to_task_fn=self._genes_to_task,
                        type_pools=self._type_pools,
                        available_params=self._available_params,
                        required_params=self._required_params,
                        seek_bad=self.seek_bad,
                        base_dir=self.config.base_dir,
                        entity=self.entity,
                        method=self.method,
                        product=_product,
                    )
                except Exception as err:
                    logger.debug(f"Agentic learner init failed for {self.entity}: {err}")
                    self._agentic_learner = None
            else:
                self._agentic_learner = None
        else:
            self._agentic_learner = None

    def _build_type_pools(self):
        """Build a {param_name: [compatible_inputs]} map for __init__ + method params."""
        if not self._entity_cls:
            return {}

        from rizza.helpers.typed_inputs import _parse_single_annotation, get_compatible_inputs

        all_inputs = list(entity_tester.EntityTester.pull_input_methods(exclude=["long"]).keys())
        known_entities = entity_tester.EntityTester.pull_entities()
        known_entity_names_lower = {name.lower(): name for name in known_entities}
        pools = {}

        for annotations in (
            getattr(self._entity_cls.__init__, "__annotations__", {}),
            getattr(self._method, "__annotations__", {}) if self._method else {},
        ):
            for param, annotation in annotations.items():
                if param == "return" or param in pools:
                    continue
                field_info = _parse_single_annotation(annotation)
                # If not already an entity ref, check if param name implies one:
                # - ends in '_id' or '_ids' and the prefix matches a known entity name
                if not field_info.get("entity"):
                    entity_name = _entity_from_param_name(param, known_entity_names_lower)
                    if entity_name:
                        field_info = {**field_info, "entity": entity_name}
                pools[param] = get_compatible_inputs(field_info, all_inputs, field_name=param)

        return pools

    def _verify_organism(self, organism):
        """Re-run the organism's genes N more times to confirm it's not a fluke.

        :returns: True if all verification runs pass; False otherwise.
        """
        verify_count = getattr(self.config.rizza.genetics, "explore_verify_count", 2)
        if verify_count <= 0:
            return True
        task = self._genes_to_task(organism.genes)
        for _ in range(verify_count):
            try:
                result = task.execute()
            except RecursionError:
                return False
            if "pass" not in result:
                return False
        return True

    def _save_organism(self, test):
        """Save the test organism to the appropriate file in data/genetic_tests."""
        test_file = self.config.base_dir.joinpath(f"data/genetic_tests/{self.entity}.yaml")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = yaml.load(test_file.open("r+"), Loader=yaml.FullLoader) or {}
        except FileNotFoundError:
            existing = {}
        task = self._genes_to_task(test.genes)
        for k, v in list(task.arg_dict.items()):
            if v == "genetic_unknown":
                task.arg_dict[k] = "genetic_known"
        existing[self.test_name] = attr.asdict(task, filter=lambda a, value: a.name != "config")
        yaml.dump(existing, test_file.open("w+"), default_flow_style=False)

    def _load_test(self):
        """Load in the last test stored in data/genetic_tests, if any exist.

        :returns: 2-list [param_names, param_inputs] or False.
        """
        test_file = self.config.base_dir.joinpath(f"data/genetic_tests/{self.entity}.yaml")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        if test_file.exists():
            tests = yaml.load(test_file.open("r"), Loader=yaml.FullLoader) or {}
            best = tests.get(self.test_name, False)
            if best and "arg_dict" in best:
                arg_dict = best["arg_dict"]
                return [list(arg_dict.keys()), list(arg_dict.values())]
        else:
            test_file.touch()
        return False

    def _judge(self, result=None, mock=False):
        """Return a numeric value for the given result."""
        if mock:
            return random.randint(-1000, 1000)
        total = 0
        for criteria, points in self.config.rizza.genetics.criteria.items():
            if dict_search(criteria, result):
                total += points
        return total

    def _genes_to_task(self, genes):
        """Turn a 2-list gene into an EntityTestTask.

        :param genes: [param_names, param_inputs]
        """
        # Deduplicate params (breeding/mutation can introduce repeats); keep first occurrence.
        seen = set()
        arg_dict = {}
        for param, inpt in zip(genes[0], genes[1], strict=False):
            if param not in seen:
                seen.add(param)
                arg_dict[param] = inpt
        return entity_tester.EntityTestTask(
            entity=self.entity,
            method=self.method,
            arg_dict=arg_dict,
            config=self.config,
        )

    def _create_gene_base(self):
        """Create a valid genetic base to evolve on.

        Required params (no default) are always included. Additional optional
        params are randomly sampled on top.

        :returns: 2-list [param_names, param_inputs]
        """
        all_inputs = list(
            entity_tester.EntityTester.pull_input_methods(exclude=["long", "genetic"]).keys()
        )

        if not self._available_params:
            return [[], []]

        # Always start with required params
        params = [p for p in self._available_params if p in self._required_params]
        optional = [p for p in self._available_params if p not in self._required_params]

        max_initial = getattr(self.config.rizza.genetics, "initial_max_gene_params", 3)
        extra_count = max(0, random.randint(0, min(max_initial, len(optional))) - len(params))
        if extra_count > 0 and optional:
            params.extend(random.sample(optional, min(extra_count, len(optional))))

        param_inputs = []
        for param in params:
            pool = self._type_pools.get(param, all_inputs)
            if param in self._required_params:
                pool = [g for g in pool if not g.startswith("genetic_")]
                if not pool:
                    pool = all_inputs
            param_inputs.append(random.choice(pool) if pool else random.choice(all_inputs))

        return [params, param_inputs]

    def _apply_agentic_improvements(
        self, org_results, fitness_cache, population, generation, suffix=""
    ):
        """Run agentic learner on one generation's results. Returns True if a pass was found."""
        if self._agentic_learner is None or not org_results:
            return False
        improvements = self._agentic_learner.learn_from_generation(org_results, fitness_cache)
        for org, new_genes, new_points, new_result in improvements:
            org.genes = new_genes
            org.points = new_points
            fitness_cache[str(new_genes)] = (new_result, new_points)
            if "pass" in new_result and not self.seek_bad and self._verify_organism(org):
                self._save_organism(org)
                logger.info(
                    "Agentic learning found a passing payload"
                    f" at generation {generation}!{' ' + suffix if suffix else ''}"
                )
                return True
        if improvements:
            population.sort_population()
        return False

    def run(self, mock=False, save_only_passed=True):
        """Run a population attempting to maximize desired results."""
        if not self._method and not mock:
            logger.warning(
                f"GeneticTester: Method '{self.method}' on entity '{self.entity}' not found."
                " Cannot run genetic test."
            )
            return None

        genetics_cfg = self.config.rizza.genetics
        try:
            population = genetics.Population(
                gene_base=[self._create_gene_base()],
                population_count=self.population_count,
                generator_function=self._create_gene_base,
                gene_length=1,
                mutate=True,
                rev_pop_sort=not self.seek_bad,
                crossover_method=getattr(genetics_cfg, "crossover_method", "single_point"),
            )
        except Exception as err:
            logger.error(f"Unable to create a population due to: {err}")
            return False

        if not self.fresh:
            best = self._load_test()
            if best:
                population.population[0].genes = best

        depth = max(0, getattr(genetics_cfg, "recursion_depth", 0))
        indent = "  " * depth

        _owns_progress = getattr(self.config, "_progress", None) is None
        if _owns_progress:
            self.config._progress = _make_progress()
            self.config._progress.start()

        progress = self.config._progress
        gen_label = f"{indent}[bold]{self.entity}[/bold].[dim]{self.method}[/dim]"
        gen_task = progress.add_task(gen_label, total=self.max_generations)
        org_task = progress.add_task(
            f"{indent}  [dim]generation[/dim]",
            total=self.population_count,
            visible=False,
        )

        _fitness_cache = {}
        try:
            for generation in range(self.max_generations):
                _org_results = []
                progress.update(org_task, completed=0, total=self.population_count, visible=True)

                population.population.sort(key=lambda o: len(o.genes[0]))
                to_remove = set()
                for organism in population.population:
                    gene_key = str(organism.genes)
                    if not mock and gene_key in _fitness_cache:
                        result, organism.points = _fitness_cache[gene_key]
                    else:
                        logger.debug(f"Testing {organism}")
                        task = self._genes_to_task(organism.genes)
                        try:
                            result = task.execute(mock)
                        except RecursionError:
                            logger.warning(
                                f"RecursionError testing {organism}; removing from population."
                            )
                            to_remove.add(id(organism))
                            progress.advance(org_task)
                            continue
                        organism.points = self._judge(result, mock)
                        if not mock:
                            _fitness_cache[gene_key] = (result, organism.points)
                    progress.advance(org_task)
                    if not mock:
                        _org_results.append((organism, result))

                    if "pass" in result and not mock and not self.seek_bad:
                        if not self._verify_organism(organism):
                            logger.debug(
                                "Organism failed verification — not saving"
                                f" (generation {generation})"
                            )
                            continue
                        self._save_organism(organism)
                        success_msg = "Success! Generation {} passed with:\n{}".format(
                            generation,
                            yaml.dump(
                                attr.asdict(
                                    self._genes_to_task(organism.genes),
                                    filter=lambda a, value: a.name != "config",
                                ),
                                default_flow_style=False,
                            ),
                        )
                        logger.info(success_msg)
                        progress.console.print(
                            f"[bold green]✓[/bold green] "
                            f"[bold]{self.entity}.{self.method}[/bold] "
                            f"passed at generation {generation}!"
                        )
                        return True

                population.population = [
                    o for o in population.population if id(o) not in to_remove
                ]
                if not population.population:
                    progress.update(gen_task, advance=1)
                    progress.update(org_task, visible=False)
                    continue

                population.sort_population()
                best = population.population[0]
                progress.update(
                    gen_task,
                    advance=1,
                    description=f"{gen_label} [green]best={best.points}[/green]",
                )
                progress.update(org_task, visible=False)
                if self._apply_agentic_improvements(
                    _org_results, _fitness_cache, population, generation
                ):
                    return True
                population.breed_population(
                    type_pools=self._type_pools,
                    tournament_size=getattr(genetics_cfg, "tournament_size", 3),
                    elite_percentage=getattr(genetics_cfg, "elite_percentage", 5),
                    immigration_rate=getattr(genetics_cfg, "immigration_rate", 5),
                    available_genes=self._available_params,
                    required_genes=self._required_params,
                )

            if not mock and not save_only_passed and population.population:
                self._save_organism(population.population[0])
            if not mock and not self.seek_bad:
                progress.console.print(
                    f"[bold yellow]✗[/bold yellow] "
                    f"[bold]{self.entity}.{self.method}[/bold] "
                    f"exhausted {self.max_generations} generations without passing"
                )
        finally:
            progress.remove_task(org_task)
            progress.remove_task(gen_task)
            if _owns_progress:
                self.config._progress.stop()
                self.config._progress = None

    def run_best(self):
        """Pull the best saved test, if any, run it, and return the id.

        Sets replay mode via contextvars so that genetic_unknown skips
        exploration and only replays saved tests.  Thread-safe — no shared
        config mutation.
        """
        token = _replay_mode.set(True)
        try:
            test = self._load_test()
            if test:
                task = self._genes_to_task(test)
                logger.info(f"Creating {self.entity}...")
                try:
                    result = task.execute()
                except RecursionError:
                    logger.warning(f"RecursionError in run_best for {self.entity}; returning -1.")
                    return -1
                if "pass" in result:
                    response = result["pass"]
                    if isinstance(response, dict):
                        entity_id = response.get("id")
                        if entity_id is None and isinstance(response.get("result"), dict):
                            entity_id = response["result"].get("id")
                        return entity_id if entity_id is not None else -1
            return -1
        finally:
            _replay_mode.reset(token)

    def run_validation(self):
        """Load and execute the saved test; return full validation details or None.

        Unlike run_best(), this captures actual resolved argument values and the full
        API response for reporting purposes.

        Sets replay mode — see run_best() docstring.
        """
        token = _replay_mode.set(True)
        try:
            test = self._load_test()
            if not test:
                return None
            task = self._genes_to_task(test)
            try:
                details = task.execute(_return_details=True)
            except RecursionError:
                logger.warning(f"RecursionError in run_validation for {self.entity}; skipping.")
                return None
            result_dict = details["result"]
            resolved_args = details["resolved_args"]
            passed = "pass" in result_dict
            return {
                "test_name": self.test_name,
                "entity": self.entity,
                "method": self.method,
                "mode": "negative" if self.seek_bad else "positive",
                "passed": passed,
                "arg_dict": dict(task.arg_dict),
                "resolved_args": {k: _safe_str(v) for k, v in resolved_args.items()},
                "response": result_dict.get("pass") if passed else result_dict.get("fail"),
            }
        finally:
            _replay_mode.reset(token)


@attr.s()
class AsyncGeneticEntityTester(GeneticEntityTester):
    """An asynchronous version of the GeneticEntityTester."""

    max_running = attr.ib(default=25)

    def __attrs_post_init__(self):
        """Setup our remaining helpers."""
        super().__attrs_post_init__()
        self.max_running = asyncio.Semaphore(self.max_running)
        self._results = asyncio.Queue()

    async def _run_org(self, organism, mock=False):
        async with self.max_running:
            task = self._genes_to_task(organism.genes)
            try:
                result = await self.loop.run_in_executor(None, task.execute, mock)
            except RecursionError:
                logger.warning(f"RecursionError testing {organism}; removing from population.")
                await self._results.put((None, organism))
                return
            except Exception as err:
                logger.error(err)
                result = "Unhandled Exception"
        organism.points = self._judge(result, mock)
        logger.debug(f"Tested {organism}")
        await self._results.put((result, organism))

    async def test_population(self, mock=False):
        """Run the tests passed in and return the log file."""
        tasks = [
            asyncio.ensure_future(self._run_org(org, mock)) for org in self._population.population
        ]
        await asyncio.wait(tasks)

    def run(self, mock=False, save_only_passed=True):
        """Run a population attempting to maximize desired results."""
        if not self._method and not mock:
            logger.warning(f"{self.entity} does not have the method {self.method}")
            return None

        genetics_cfg = self.config.rizza.genetics
        try:
            self._population = genetics.Population(
                gene_base=[self._create_gene_base()],
                population_count=self.population_count,
                generator_function=self._create_gene_base,
                gene_length=1,
                mutate=True,
                rev_pop_sort=not self.seek_bad,
                crossover_method=getattr(genetics_cfg, "crossover_method", "single_point"),
            )
        except Exception as err:
            logger.error(f"Unable to create a population due to: {err}")
            return False

        if not self.fresh:
            best = self._load_test()
            if best:
                self._population.population[0].genes = best

        depth = max(0, getattr(genetics_cfg, "recursion_depth", 0))
        indent = "  " * depth

        _owns_progress = getattr(self.config, "_progress", None) is None
        if _owns_progress:
            self.config._progress = _make_progress()
            self.config._progress.start()

        progress = self.config._progress
        gen_label = (
            f"{indent}[bold]{self.entity}[/bold].[dim]{self.method}[/dim] [italic]async[/italic]"
        )
        gen_task = progress.add_task(gen_label, total=self.max_generations)
        org_task = progress.add_task(
            f"{indent}  [dim]generation[/dim]",
            total=self.population_count,
            visible=False,
        )

        _fitness_cache = {}
        try:
            for generation in range(self.max_generations):
                _org_results = []
                progress.update(org_task, completed=0, total=self.population_count, visible=True)

                self.loop = asyncio.new_event_loop()
                self._results.empty()
                self.loop.run_until_complete(self.test_population(mock))
                self.loop.close()

                to_remove = set()
                passed_organism = None
                while self._results.qsize() > 0:
                    result, organism = self._results.get_nowait()
                    if result is None:
                        to_remove.add(id(organism))
                        progress.advance(org_task)
                        continue
                    if not mock:
                        gene_key = str(organism.genes)
                        _fitness_cache[gene_key] = (result, organism.points)
                        _org_results.append((organism, result))
                    if "pass" in result and not mock and not self.seek_bad:
                        passed_organism = organism
                    progress.advance(org_task)

                self._population.population = [
                    o for o in self._population.population if id(o) not in to_remove
                ]

                if passed_organism is not None and not self._verify_organism(passed_organism):
                    logger.debug(
                        "Organism failed verification — not saving"
                        f" (generation {generation}, async)"
                    )
                    passed_organism = None
                if passed_organism is not None:
                    self._save_organism(passed_organism)
                    success_msg = "Success! Generation {} passed with:\n{}".format(
                        generation,
                        yaml.dump(
                            attr.asdict(
                                self._genes_to_task(passed_organism.genes),
                                filter=lambda a, value: a.name != "config",
                            ),
                            default_flow_style=False,
                        ),
                    )
                    logger.info(success_msg)
                    progress.console.print(
                        f"[bold green]✓[/bold green] "
                        f"[bold]{self.entity}.{self.method}[/bold] "
                        f"passed at generation {generation}! (async)"
                    )
                    return True

                if not self._population.population:
                    progress.update(gen_task, advance=1)
                    progress.update(org_task, visible=False)
                    continue

                self._population.sort_population()
                best = self._population.population[0]
                progress.update(
                    gen_task,
                    advance=1,
                    description=f"{gen_label} [green]best={best.points}[/green]",
                )
                progress.update(org_task, visible=False)
                if self._apply_agentic_improvements(
                    _org_results, _fitness_cache, self._population, generation, suffix="(async)"
                ):
                    return True
                self._population.breed_population(
                    type_pools=self._type_pools,
                    tournament_size=getattr(genetics_cfg, "tournament_size", 3),
                    elite_percentage=getattr(genetics_cfg, "elite_percentage", 5),
                    immigration_rate=getattr(genetics_cfg, "immigration_rate", 5),
                    available_genes=self._available_params,
                )

            if not mock and not save_only_passed and self._population.population:
                self._save_organism(self._population.population[0])
            if not mock and not self.seek_bad:
                progress.console.print(
                    f"[bold yellow]✗[/bold yellow] "
                    f"[bold]{self.entity}.{self.method}[/bold] "
                    f"exhausted {self.max_generations} generations without passing"
                )
        finally:
            progress.remove_task(org_task)
            progress.remove_task(gen_task)
            if _owns_progress:
                self.config._progress.stop()
                self.config._progress = None
