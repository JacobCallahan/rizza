"""Interface adapter protocol and concrete implementations.

Provides a common abstraction for different product interfaces (API, CLI, UI)
so that rizza's testing engine can work against any of them.
"""
import abc
import logging

import attr

logger = logging.getLogger(__name__)


@attr.s(slots=True)
class InteractionResult:
    """Interface-agnostic result that the RL agent and fitness judge consume."""

    success = attr.ib()
    output_text = attr.ib()
    status_category = attr.ib()
    error_class = attr.ib()
    raw = attr.ib()
    validation_errors = attr.ib(factory=dict)
    missing_params = attr.ib(factory=list)


class InterfaceAdapter(abc.ABC):
    """Abstract base for interface-specific loading and result adaptation."""

    @abc.abstractmethod
    def load_module(self, path):
        """Load the generated library module from the given path."""

    @abc.abstractmethod
    def get_base_class(self):
        """Return the entity base class from the loaded module."""

    @abc.abstractmethod
    def get_connection_class(self):
        """Return the connection class from the loaded module."""

    @abc.abstractmethod
    def init_connection(self, hostname, username, password):
        """Establish a connection to the target product."""

    @abc.abstractmethod
    def adapt_result(self, raw_result):
        """Convert a raw test result into an InteractionResult."""

    @abc.abstractmethod
    def reset(self):
        """Clear any cached module state."""


class APIInterfaceAdapter(InterfaceAdapter):
    """Wraps existing apix_loader for the API interface."""

    def load_module(self, path):
        from rizza import apix_loader

        return apix_loader.get_apix_module(path=path)

    def get_base_class(self):
        from rizza import apix_loader

        return apix_loader.get_satellite_class()

    def get_connection_class(self):
        from rizza import apix_loader

        return apix_loader.get_connection_class()

    def init_connection(self, hostname, username, password):
        conn_cls = self.get_connection_class()
        conn_cls(hostname=hostname, auth=f"{username}:{password}")

    def adapt_result(self, raw_result):
        if "pass" in raw_result:
            return InteractionResult(
                success=True,
                output_text=str(raw_result["pass"]),
                status_category="success",
                error_class="",
                raw=raw_result,
            )
        fail_data = raw_result.get("fail", {})
        error_class = _extract_error_class(fail_data)
        output_text = _flatten_to_text(fail_data)
        status_category = _categorize_api(fail_data, error_class)
        from rizza.helpers.misc import extract_missing_params, extract_validation_errors

        return InteractionResult(
            success=False,
            output_text=output_text,
            status_category=status_category,
            error_class=error_class,
            raw=raw_result,
            validation_errors=extract_validation_errors(fail_data),
            missing_params=extract_missing_params(fail_data),
        )

    def reset(self):
        from rizza import apix_loader

        apix_loader.reset()


class CLIInterfaceAdapter(InterfaceAdapter):
    """Stub adapter for the CLI interface."""

    def load_module(self, path):
        raise NotImplementedError(
            "CLI interface not yet implemented. Set interface to 'api' in rizza.pconf."
        )

    def get_base_class(self):
        raise NotImplementedError("CLI interface not yet implemented.")

    def get_connection_class(self):
        raise NotImplementedError("CLI interface not yet implemented.")

    def init_connection(self, hostname, username, password):
        raise NotImplementedError("CLI interface not yet implemented.")

    def adapt_result(self, exit_code, stdout, stderr):
        success = exit_code == 0
        output_text = stderr if not success else stdout
        if exit_code == 0:
            category = "success"
        elif exit_code in (500, 502, 503):
            category = "server_error"
        else:
            category = "client_error"
        return InteractionResult(
            success=success,
            output_text=output_text or "",
            status_category=category,
            error_class=f"ExitCode_{exit_code}",
            raw={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
        )

    def reset(self):
        pass


def _extract_error_class(fail_data):
    if not isinstance(fail_data, dict) or not fail_data:
        return "unhandled"
    return next(iter(fail_data))


def _flatten_to_text(data):
    if isinstance(data, dict):
        parts = [_flatten_to_text(v) for v in data.values()]
    elif isinstance(data, list | tuple):
        parts = [_flatten_to_text(item) for item in data]
    elif isinstance(data, bytes | bytearray):
        parts = [data.decode("utf-8", errors="replace")]
    elif data is not None:
        parts = [str(data)]
    else:
        parts = []
    return " ".join(p for p in parts if p)


def _categorize_api(fail_data, error_class):
    if error_class == "HTTPError":
        text = _flatten_to_text(fail_data.get("HTTPError", {}))
        for code in ("500", "501", "502", "503", "504"):
            if code in text:
                return "server_error"
        return "client_error"
    if error_class in ("TypeError", "ValueError", "KeyError", "AttributeError", "RuntimeError"):
        return "client_error"
    return "unknown"
