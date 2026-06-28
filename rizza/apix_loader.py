"""Dynamic loader for the apix_generated library."""
import importlib.util
import os
from pathlib import Path
import sys

_module = None
_DEFAULT_PATH = "~/rizza/apix_generated.py"


def get_apix_module(path=None):
    """Load and cache the apix_generated module.

    :param path: Override the path to apix_generated.py. Falls back to the
        APIX_LIB_PATH environment variable, then to the default location.
    """
    global _module
    if _module is not None:
        return _module

    resolved_path = path or os.environ.get("APIX_LIB_PATH") or _DEFAULT_PATH
    resolved_path = Path(resolved_path).expanduser().resolve()

    if not resolved_path.exists():
        raise FileNotFoundError(
            f"apix_generated library not found at {resolved_path}. "
            "Set APIX_LIB_PATH env var or configure apix_lib_path in your rizza.pconf."
        )

    spec = importlib.util.spec_from_file_location("apix_generated", resolved_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["apix_generated"] = module
    spec.loader.exec_module(module)
    _module = module
    return _module


def get_satellite_class():
    """Return the Satellite base class from the loaded apix module."""
    return get_apix_module().Satellite


def get_connection_class():
    """Return the APIConnection class from the loaded apix module."""
    return get_apix_module().APIConnection


def reset():
    """Clear the cached module (useful for testing)."""
    global _module
    _module = None
