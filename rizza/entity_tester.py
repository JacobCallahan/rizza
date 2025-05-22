"""A module that provides utilities to test Nailgun entities."""
import inspect

import attr
from logzero import logger
# from nailgun import entities # FIXME: Nailgun removed

from rizza.helpers import inputs
from rizza.helpers.misc import (
    combination_list,
    dictionary_exclusion,
    form_input,
    handle_exception,
    map_field_inputs,
    product_list,
)


@attr.s()
class EntityTester:
    """This class implements methods useful in testing Nailgun entities.

    :param entity: Nailgun entity, or entity name. (Case sensitive)
    :param fields: Dictionary mapping nailgun field names to nailgun input
        methods.
    :param methods: Dictionary mapping nailgun method names to their methods.
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
                raise Exception(f"Entity {self.entity} not found.")

        if self.entity:
            self.fields = self.pull_fields(self.entity, exclude=field_exclude)
            self.methods = self.pull_methods(self.entity, exclude=method_exclude)

    def test_entity(self, task=None, depth=0):
        """Run an ehaustive test of the entity."""
        if not task:
            return None
        return 0

    def brute_force(self, max_fields=None, max_inputs=None):
        """Create a generator of tests for all entity permutations.

        :param max_fields: The limit of fields desired for testing.
        :param max_inputs: The limit of inputs desired for testing.

        :returns: A generator of EntityTestTask instances.
        """
        entity_name = self.entity.__name__

        input_list = self.pull_input_methods(exclude=["long", "genetic"]).keys()
        if not max_inputs:
            max_inputs = len(input_list)
        input_combos = product_list(input_list, max_inputs)

        method_combo_dict = {}
        for method in self.methods:
            method_combo_dict[method] = []
            args = self.pull_args(self.methods[method])
            method_combo_dict[method].extend(
                map_field_inputs(
                    args,
                    product_list(input_list, max_inputs if max_inputs <= len(args) else len(args)),
                )
            )

        field_combo_list = combination_list(self.fields, max_fields)
        for combo in field_combo_list:
            # Map all the possible input combinations to the fields
            field_inputs = map_field_inputs(combo, input_combos)
            for fi_dict in field_inputs:
                for method in method_combo_dict:
                    for mc_dict in method_combo_dict[method]:
                        yield EntityTestTask(
                            entity=entity_name, method=method, field_dict=fi_dict, arg_dict=mc_dict
                        )

    @staticmethod
    def pull_entities(exclude=None):
        """Return a dictionary of nailgun entities."""
        # FIXME: Nailgun removed. Returning empty dict.
        logger.warning("Nailgun entities are not available. Returning empty list.")
        return {}
        # edict = {
        #     entity: entities.__dict__[entity]
        #     for entity in dir(entities)
        #     if entity[0] != "_" and entity[0].istitle() and not entity.isupper()
        # }
        # return dictionary_exclusion(edict, exclude)

    @staticmethod
    def pull_methods(entity=None, exclude=None):
        """Return a dictionary of methods belonging to an entity."""
        # FIXME: Nailgun removed. Returning empty dict.
        if entity:
            logger.warning(f"Nailgun entity {entity} methods are not available. Returning empty list.")
            # try:
            #     methods = inspect.getmembers(entity(), predicate=inspect.ismethod)
            # except TypeError as err:
            #     # Failed nailgun's _check_for_value
            #     logger.error(f"Unable to init {entity} due to {err}")
            #     return None
            # mdict = {name: method for name, method in methods if "__" not in name}
            # return dictionary_exclusion(mdict, exclude)
        return {}


    @staticmethod
    def pull_fields(entity=None, exclude=None):
        """Return a dictionary of fields belonging to an entity's method."""
        # FIXME: Nailgun removed. Returning empty dict.
        if entity:
            logger.warning(f"Nailgun entity {entity} fields are not available. Returning empty list.")
        #     try:
        #         entity_inst = entity()
        #         fields = entity_inst._fields
        #     except Exception as err:
        #         # Failed nailgun's _check_for_value or entity doens't have _fields
        #         logger.error(f"Unable to init {entity} due to {err}")
        #         return None
        #     return dictionary_exclusion(fields, exclude)
        return {}

    @staticmethod
    def pull_args(method=None):
        """Return a list of args belonging to an entity's method."""
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

    :params entity: A string matching an entity class.
    :params method: A string matching an method class.
    :params fields: A dict of method fields to pass in.
    :params inputs: A dict of field inputs to pass in.

    """

    entity = attr.ib()
    method = attr.ib()
    field_dict = attr.ib(validator=attr.validators.instance_of(dict))
    arg_dict = attr.ib(validator=attr.validators.instance_of(dict))
    config = attr.ib(default=None, repr=False)

    def execute(self, mock=False):
        """Execute the task.

        :params mock: A bool switch to turn off true execution.

        :returns: Either a valid nailgun entity or an exception object.
        """
        if mock:
            return attr.asdict(self)

        imeths = EntityTester.pull_input_methods()
        cut_list = []
        for field, inpt in self.field_dict.items():
            self.field_dict[field] = form_input(inpt, imeths, field, self.config)
            if self.field_dict[field] == "~":
                cut_list.append(field)
        for entry in cut_list:
            del self.field_dict[entry]

        self.arg_dict = {
            arg: imeths.get(inpt, lambda inpt=inpt: inpt)()
            for arg, inpt in self.arg_dict.items()
            if "genetic" not in inpt
        }

        logger.debug(
            "Executing: {} {} with fields: {} and args {}".format(
                self.entity, self.method, self.field_dict, self.arg_dict
            )
        )
        # FIXME: Nailgun removed. This part will likely not work as expected.
        pulled_entities = EntityTester.pull_entities()
        if not pulled_entities or self.entity not in pulled_entities:
            logger.error(f"Entity {self.entity} not found or nailgun entities unavailable.")
            return {"fail": f"Entity {self.entity} not found or nailgun entities unavailable."}

        try:
            # entity_instance = pulled_entities[self.entity](**self.field_dict)
            # result = getattr(entity_instance, self.method)(**self.arg_dict)
            # if not isinstance(result, dict):
            #     result = result.to_json_dict()
            # logger.debug(f"pass: {result}")
            # return {"pass": result}
            logger.warning("Nailgun entity execution skipped.")
            return {"skipped": "Nailgun entity execution skipped due to nailgun removal."}
        except Exception as e:
            handled = handle_exception(e)
            logger.debug(f"fail: {handled}")
            return {"fail": handled}


@attr.s(slots=True)
class MaIMap:
    """Provide a map between method fields and input functions.

    :params fields: A dict of fields (field name, field).
    :params inputs: A dict of tuples (input name, input function).
    :params mai_map: A pre-existing map (optional).
    """

    fields = attr.ib(validator=attr.validators.instance_of(dict))
    inputs = attr.ib(validator=attr.validators.instance_of(dict))
    mai_map = attr.ib(default=[])

    def __attrs_post_init__(self):
        """Setup the instance."""
        if not self.mai_map:
            self.mai_map = [[None for x in self.x_labels] for y in self.y_labels]

    def point(self, x, y, value=None):
        """Map must be initialized before using this method."""
        if value:
            self.mai_map[x][y] = value
        return {
            "x label": self.x_labels[x],
            "y label": self.y_labels[y],
            "value": self.mai_map[x][y],
        }

    def find(self, needle=None):
        """Search the map for the specified value then return
        a list of points where that value exists.
        """
        if not needle:
            return []
        return [
            (x, y)
            for x in range(len(self.mai_map))
            for y in range(len(self.mai_map[x]))
            if str(needle) in str(self.mai_map[x][y])
        ]

    @property
    def x_labels(self):
        """Return the labels on the x axis."""
        return list(self.fields.keys())

    @property
    def y_labels(self):
        """Return the labels on the y axis."""
        return list(self.inputs.keys())
