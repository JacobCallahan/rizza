"""Registry for interface adapters."""
from rizza.interface_adapter import APIInterfaceAdapter, CLIInterfaceAdapter

_ADAPTERS = {
    "api": APIInterfaceAdapter,
    "cli": CLIInterfaceAdapter,
}

_current = None


def get_adapter(interface_name):
    """Instantiate and return an adapter for the given interface name."""
    cls = _ADAPTERS.get(interface_name)
    if cls is None:
        raise ValueError(f"Unknown interface: {interface_name!r}. Available: {list(_ADAPTERS)}")
    return cls()


def set_current(adapter):
    """Set the active adapter for the current session."""
    global _current
    _current = adapter


def get_current():
    """Return the active adapter, or None if not initialized."""
    return _current


def reset():
    """Clear the current adapter."""
    global _current
    _current = None
