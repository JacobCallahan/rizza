"""A module that provides utilities to test apix entities."""
import inspect
import logging

import attr

logger = logging.getLogger(__name__)

from rizza.helpers import inputs
from rizza.helpers.misc import (
    dictionary_exclusion,
    form_input,
    handle_exception,
)


def _parse_annotations(method):
    """Return a {param_name: field_info} dict from a method's annotations.

    :param method: A callable with optional __annotations__.
    :returns: Dict mapping parameter names to field_info dicts.
    """
    from rizza.helpers.typed_inputs import _parse_single_annotation

    annotations = getattr(method, "__annotations__", {})
    result = {}
    for param, annotation in annotations.items():
        if param == "return":
            continue
        result[param] = _parse_single_annotation(annotation)
    return result


@attr.s()
class EntityTester:
    """This class implements methods useful in testing apix entities.

    :param entity: Entity class, or entity name (case sensitive).
    :param fields: Dictionary mapping field names to field_info dicts.
    :param methods: Dictionary mapping method names to their callables.
    """

    entity = attr.ib()
    fields = attr.ib(default=None)
    methods = attr.ib(default=None)

    def prep(self, entity=None, field_exclude=None, method_exclude=None):
        """Gather information about the current entity."""
        if isinstance(self.entity, str):
            entity = self.entity
        if entity:
            elist = self.pull_entities()
            if entity in elist:
                self.entity = elist[entity]
            elif entity in elist.values():
                self.entity = entity
            else:
                logger.warning(f"Entity {self.entity} not found.")
                return

        if self.entity:
            self.fields = self.pull_fields(self.entity, exclude=field_exclude)
            self.methods = self.pull_methods(self.entity, exclude=method_exclude)

    def test_entity(self, task=None, depth=0):
        """Run an exhaustive test of the entity."""
        if not task:
            return None
        return 0

    @staticmethod
    def pull_entities(exclude=None):
        """Return a dict of {name: class} for all apix entity classes."""
        try:
            from rizza import apix_loader

            module = apix_loader.get_apix_module()
            Satellite = apix_loader.get_satellite_class()
        except Exception as err:
            logger.warning(f"Could not load apix module: {err}")
            return {}

        entities = {
            name: cls
            for name, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Satellite) and cls is not Satellite
        }
        return dictionary_exclusion(entities, exclude)

    @staticmethod
    def pull_methods(entity=None, exclude=None):
        """Return a dict of {name: method} for an entity's API methods."""
        if entity is None:
            return {}

        try:
            from rizza import apix_loader

            Satellite = apix_loader.get_satellite_class()
        except Exception as err:
            logger.warning(f"Could not load apix module: {err}")
            return {}

        api_methods = getattr(entity, "_api_methods", None)
        if api_methods:
            methods = {
                name: getattr(entity, name) for name in api_methods if hasattr(entity, name)
            }
        else:
            # Fall back: subtract Satellite base methods from entity's methods
            base_methods = set(dir(Satellite))
            methods = {
                name: getattr(entity, name)
                for name in dir(entity)
                if not name.startswith("_")
                and name not in base_methods
                and callable(getattr(entity, name, None))
            }

        return dictionary_exclusion(methods, exclude)

    @staticmethod
    def pull_fields(entity=None, exclude=None, method=None):
        """Return a merged {param_name: field_info} dict from entity API method annotations.

        :param entity: Entity class.
        :param exclude: Fields to exclude.
        :param method: Optional method name string to scope to a single method.
        """
        if entity is None:
            return {}

        api_methods = getattr(entity, "_api_methods", None)
        if method:
            target_methods = [method] if api_methods and method in api_methods else []
            if not target_methods and hasattr(entity, method):
                target_methods = [method]
        else:
            target_methods = api_methods or []

        merged = {}
        for mname in target_methods:
            meth = getattr(entity, mname, None)
            if meth:
                merged.update(_parse_annotations(meth))

        return dictionary_exclusion(merged, exclude)

    @staticmethod
    def pull_args(method=None):
        """Return a list of parameter names for a method (excluding 'self')."""
        if method:
            return [arg for arg in inspect.signature(method).parameters if arg != "self"]

    @staticmethod
    def pull_input_methods(exclude=None):
        """Return a dictionary of input methods."""
        indict = {meth: inputs.__dict__[meth] for meth in dir(inputs) if "__" not in meth}
        return dictionary_exclusion(indict, exclude)


@attr.s(slots=True)
class EntityTestTask:
    """An Entity test task object that stores relevant information.

    :param entity: A string matching an entity class name.
    :param method: A string matching a method name.
    :param arg_dict: A dict mapping parameter names to input method names.
    :param config: Config instance (used for dependency resolution).
    """

    entity = attr.ib()
    method = attr.ib()
    arg_dict = attr.ib(validator=attr.validators.instance_of(dict))
    config = attr.ib(default=None, repr=False)

    def execute(self, mock=False):
        """Execute the task.

        :param mock: Return task dict without making real API calls.
        :returns: Dict with 'pass', 'fail', or 'skipped' key.
        """
        if mock:
            return attr.asdict(self)

        imeths = EntityTester.pull_input_methods()

        # Resolve arg_dict input method names to actual values
        # Build field_info map from entity annotations for type-aware resolution
        pulled_entities = EntityTester.pull_entities()
        entity_cls = pulled_entities.get(self.entity)
        if not entity_cls:
            logger.error(f"Entity '{self.entity}' not found in apix module.")
            return {"fail": f"Entity '{self.entity}' not found."}

        method_obj = getattr(entity_cls, self.method, None)
        if not method_obj:
            logger.error(f"Method '{self.method}' not found on entity '{self.entity}'.")
            return {"fail": f"Method '{self.method}' not found."}

        field_info_map = _parse_annotations(method_obj)

        resolved_args = {}
        cut_list = []
        for arg, inpt in self.arg_dict.items():
            field_info = field_info_map.get(arg)
            value = form_input(inpt, imeths, arg, self.config, field_info)
            if value == "~":
                cut_list.append(arg)
            else:
                resolved_args[arg] = value
        for _ in cut_list:
            pass  # skip unresolvable dependency args

        logger.debug(f"Executing: {self.entity}.{self.method}({resolved_args})")

        try:
            import inspect

            init_param_names = set(inspect.signature(entity_cls.__init__).parameters) - {"self"}
            init_args = {k: v for k, v in resolved_args.items() if k in init_param_names}
            method_args = {k: v for k, v in resolved_args.items() if k not in init_param_names}
            entity_inst = entity_cls(**init_args)
            try:
                result = getattr(entity_inst, self.method)(**method_args)
            except AttributeError as ae:
                if "has no attribute 'id'" not in str(ae):
                    raise
                # Method needs self.id — try to get a real ID via genetic_known
                from rizza.helpers.inputs import genetic_known

                entity_id = genetic_known(self.config, self.entity)
                if entity_id and entity_id not in (-1, "~"):
                    entity_inst.id = entity_id
                    result = getattr(entity_inst, self.method)(**method_args)
                else:
                    raise
            return {"pass": result.json() if hasattr(result, "json") else result}
        except Exception as e:
            handled = handle_exception(e)
            logger.debug(f"fail: {handled}")
            return {"fail": handled}
