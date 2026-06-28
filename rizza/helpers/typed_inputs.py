"""Type-aware input generation for apix entity method parameters."""
import random

from fauxfactory import gen_alphanumeric, gen_boolean, gen_integer


def generate_value(field_info):
    """Generate an appropriate value given parsed annotation field info.

    :param field_info: A dict with at least a 'type' key describing the field.
        Expected keys: 'type' (str), 'required' (bool), 'choices' (list, optional),
        'entity' (str, optional for entity references).
    :returns: A generated value appropriate for the field type.
    """
    if not field_info:
        return gen_alphanumeric()

    field_type = field_info.get("type", "str")
    choices = field_info.get("choices")
    entity_ref = field_info.get("entity")

    if entity_ref:
        return "genetic_known"

    if choices:
        return random.choice(choices)

    type_map = {
        "str": gen_alphanumeric,
        "int": gen_integer,
        "bool": gen_boolean,
        "dict": dict,
        "list": list,
    }

    if field_type in type_map:
        return type_map[field_type]()

    # ffTypes or unknown — fall back to alphanumeric
    return gen_alphanumeric()


def generate_method_args(entity_class, method_name, mode="typed"):
    """Build a {param_name: input_method_name} dict for a method.

    :param entity_class: The entity class (from apix_generated).
    :param method_name: The method name to generate args for.
    :param mode: 'typed' uses type hints; 'random' picks any input method.
    :returns: Dict mapping param names to input method name strings.
    """
    from rizza.entity_tester import EntityTester
    from rizza.helpers.typed_inputs import get_compatible_inputs

    method = getattr(entity_class, method_name, None)
    if method is None:
        return {}

    args = EntityTester.pull_args(method)
    all_inputs = list(EntityTester.pull_input_methods(exclude=["long"]).keys())

    if mode == "random":
        return {arg: random.choice(all_inputs) for arg in args}

    annotations = getattr(method, "__annotations__", {})
    result = {}
    for arg in args:
        if arg in annotations:
            field_info = _parse_single_annotation(annotations[arg])
            compatible = get_compatible_inputs(field_info, all_inputs)
            result[arg] = random.choice(compatible) if compatible else random.choice(all_inputs)
        else:
            result[arg] = random.choice(all_inputs)
    return result


def get_compatible_inputs(field_info, all_input_names):
    """Return input method names whose output type matches the field's expected type.

    :param field_info: Parsed annotation dict with at least a 'type' key.
    :param all_input_names: List of all available input method name strings.
    :returns: List of compatible input method name strings.
    """
    if not field_info:
        return all_input_names

    field_type = field_info.get("type", "str")
    entity_ref = field_info.get("entity")

    if entity_ref:
        return [n for n in all_input_names if "genetic" in n]

    if field_info.get("choices"):
        # Literal type — no standard fauxfactory function applies well
        return all_input_names

    type_prefix_map = {
        "str": [
            "gen_alpha",
            "gen_utf8",
            "gen_uuid",
            "gen_email",
            "gen_url",
            "gen_mac",
            "gen_ipaddr",
            "gen_iplum",
            "yum_url",
            "puppet_url",
            "content_type",
        ],
        "int": ["gen_integer", "gen_positive_integer"],
        "bool": ["gen_boolean"],
    }

    prefixes = type_prefix_map.get(field_type)
    if prefixes:
        compatible = [n for n in all_input_names if any(n.startswith(p) for p in prefixes)]
        return compatible if compatible else all_input_names

    return all_input_names


def _parse_string_annotation(s):
    """Parse a string annotation (from __future__ import annotations) into a field_info dict."""
    s = s.strip()

    required = True
    # Strip trailing | None / | NoneType
    if "| None" in s or "| NoneType" in s:
        required = False
        s = s.split("|")[0].strip()

    # Optional[X]
    if s.startswith("Optional[") and s.endswith("]"):
        return _parse_string_annotation(s[9:-1])

    # Bare primitive types
    bare = {"str": "str", "int": "int", "bool": "bool", "dict": "dict", "list": "list"}
    if s in bare:
        return {"type": bare[s], "required": required}

    # list[Entity.id] or list[something]
    if (s.startswith("list[") or s.startswith("List[")) and s.endswith("]"):
        inner = s[s.index("[") + 1 : -1].strip()
        if ".id" in inner:
            entity_name = inner.split(".")[0].strip()
            return {"type": "list", "entity": entity_name, "required": required}
        return {"type": "list", "required": required}

    # Literal['a', 'b', ...] string form — parse choices
    if s.startswith("Literal[") and s.endswith("]"):
        import ast

        inner = s[8:-1]
        try:
            choices = list(ast.literal_eval(f"({inner},)"))
        except Exception:
            choices = [c.strip().strip("'\"") for c in inner.split(",")]
        return {"type": "literal", "choices": choices, "required": required}

    # X.id format → entity reference (e.g. Organization.id)
    if s.endswith(".id") and "." in s:
        entity_name = s.split(".")[0].strip()
        if entity_name[0].isupper():
            return {"type": "int", "entity": entity_name, "required": required}

    # Bare capitalized name → treat as entity reference (e.g. ContentViewEnvironment)
    if s and s[0].isupper() and "." not in s:
        return {"type": "int", "entity": s, "required": required}

    # Unknown (ffTypes.X, etc.) → treat as str
    return {"type": "str", "required": required}


def _parse_single_annotation(annotation):
    """Parse a single annotation into a field_info dict.

    Handles: str, int, bool, dict, list, Literal[...], Optional[X] / X | None,
    and entity references of the form 'Entity.id' or 'list[Entity.id]'.
    String annotations (from __future__ import annotations) are parsed directly.
    """
    import types
    import typing

    if annotation is None:
        return {"type": "str", "required": False}

    # String annotations — emitted when the source uses `from __future__ import annotations`
    if isinstance(annotation, str):
        return _parse_string_annotation(annotation)

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", None)

    # Literal[...]
    if origin is typing.Literal:
        return {"type": "literal", "choices": list(args), "required": True}

    # Union types: Optional[X] (typing.Union) and X | None (Python 3.10+ types.UnionType)
    is_union = origin is typing.Union or isinstance(annotation, types.UnionType)
    if is_union:
        raw_args = args or getattr(annotation, "__args__", ()) or ()
        non_none = [a for a in raw_args if a is not type(None)]
        if len(non_none) == 1:
            inner_info = _parse_single_annotation(non_none[0])
            inner_info["required"] = False
            return inner_info
        return {"type": "str", "required": False}

    # list[Something]
    if origin is list and args:
        inner = args[0]
        inner_info = _parse_single_annotation(inner)
        if inner_info.get("entity"):
            return {"type": "list", "entity": inner_info["entity"], "required": False}
        return {"type": "list", "required": False}

    # Bare types
    type_map = {str: "str", int: "int", bool: "bool", dict: "dict", list: "list"}
    if annotation in type_map:
        return {"type": type_map[annotation], "required": True}

    # Entity reference heuristic: runtime type objects only (not strings, handled above)
    if hasattr(annotation, "__name__") and annotation.__name__[0].isupper():
        entity_name = annotation.__name__
        return {"type": "int", "entity": entity_name, "required": False}

    return {"type": "str", "required": False}
