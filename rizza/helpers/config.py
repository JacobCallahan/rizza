"""Project configuration helpers."""
import logging
from pathlib import Path
import shutil

import attr
from picoconf import PicoConf
import yaml

from rizza.helpers.logging import setup_logging

logger = logging.getLogger(__name__)

IMPORTED_CHUNKS = {"genetics": "genetics.pconf", "connection": "connection.pconf"}


def _version_minor(version_string):
    """'6.12.1' → '6.12'. Pass-through for 'X.Y' or non-numeric strings."""
    parts = str(version_string).split(".")
    return ".".join(parts[:2])


DEFAULT_CONFIG = {
    "genetics": {
        "population_count": 100,
        "max_generations": 10000,
        "allow_dependencies": True,
        "allow_recursion": True,
        "max_recursive_generations": 5,
        "max_recursive_depth": 3,
        "explore_verify_count": 2,
        "tournament_size": 3,
        "elite_percentage": 5,
        "immigration_rate": 5,
        "crossover_method": "single_point",
        "criteria": {
            "pass": 500,
            "fail": -200,
            "HTTPError": -200,
            "200": 1000,
            "404": -500,
            "422": -200,
            "500": -1000,
            "created": 500,
            "BadValueError": -500,
            "TypeError": -200,
        },
        "agentic": {
            "enabled": False,
            "max_candidates_per_generation": 5,
            "max_steps_per_candidate": 5,
            "bucket_similarity_threshold": 0.85,
            "use_embeddings": False,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "hf_token": "",
            "policy": {
                "alpha": 0.1,
                "gamma": 0.95,
                "epsilon": 0.3,
                "epsilon_decay": 0.995,
            },
            "reward": {
                "success": 20,
                "improved": 5,
                "new_error": 3,
                "same": -1,
                "regressed": -2,
                "server_error": -5,
                "targeted_success": 8,
            },
            "validation_override_prob": 0.5,
            "validation_override_decay": 0.995,
            "recommender_batch_size": 8,
            "recommender_epsilon_decay_per_episode": 0.998,
        },
    },
    "connection": {
        "hostname": "",
        "username": "admin",
        "password": "changeme",
    },
    "interface": "api",
    "apix_lib_path": "~/rizza/libs/satellite.py",
    "clix_lib_path": "",
    "product_name": "satellite",
    "product_version": "",
    "log_path": "logs/rizza.log",
    "log_level": "info",
    "log_file_level": "debug",
}


@attr.s()
class Config:
    """Encompassing configuration class.

    Order of preference is:
        1. Environmental Variables (via picoconf _envar_prefix in .pconf files)
        2. Configuration File(s)
        3. Defaults (DEFAULT_CONFIG)
    """

    cfg_dir = attr.ib(default="config/", cmp=False, repr=False)
    rizza = attr.ib(default=attr.Factory(dict), cmp=False)

    def __attrs_post_init__(self):
        """Load configuration from rizza.pconf using picoconf."""
        self.base_dir = Path.home().joinpath("rizza")
        if "tests" in str(self.cfg_dir):
            self.cfg_dir = Path().joinpath(self.cfg_dir)
        elif self.cfg_dir != str(Path(self.cfg_dir).absolute()):
            self.cfg_dir = self.base_dir.joinpath(self.cfg_dir)

        rizza_pconf = Path(self.cfg_dir) / "rizza.pconf"
        if rizza_pconf.exists():
            self.rizza = PicoConf(str(rizza_pconf), **DEFAULT_CONFIG)
        else:
            self.rizza = PicoConf(**DEFAULT_CONFIG)

    def load_cli_args(self, args=None, command=False):
        """Pull in any relevant settings from argparse"""
        if "project" in dir(args) and args.project == "rizza" and not args.show and not args.clear:
            logger.debug("Set rizza configuration.")

    def init_connection(self):
        """Initialize the product connection using the configured interface adapter."""
        from rizza import interface_loader

        interface = getattr(self.rizza, "interface", "api")
        adapter = interface_loader.get_adapter(interface)
        lib_path = self._get_lib_path(interface)

        adapter.load_module(path=lib_path)
        conn = self.rizza.connection
        adapter.init_connection(
            hostname=conn.hostname,
            username=conn.username,
            password=conn.password,
        )
        interface_loader.set_current(adapter)
        logger.debug(f"Connection initialized for interface={interface}, host={conn.hostname}")

    def _get_lib_path(self, interface):
        """Return the configured library path for the given interface."""
        path_map = {
            "api": getattr(self.rizza, "apix_lib_path", ""),
            "cli": getattr(self.rizza, "clix_lib_path", ""),
        }
        path = path_map.get(interface, "")
        if not path:
            raise ValueError(
                f"No lib path configured for interface {interface!r}. "
                f"Set the corresponding lib_path in rizza.pconf."
            )
        return path

    def init_logger(self, path=None, level=None, file_level=None):
        path = path or self.rizza.log_path
        level = level or self.rizza.log_level
        file_level = file_level or self.rizza.log_file_level
        setup_logging(console_level=level, file_level=file_level, log_path=path)

    def clear_rizza(self):
        """Reset rizza configuration to defaults in memory.

        Note: This does not write to disk. The on-disk .pconf files are not
        modified; only the in-memory configuration is reset to DEFAULT_CONFIG.
        """
        self.rizza = PicoConf(**DEFAULT_CONFIG)

    @staticmethod
    def _resolve_attr_key(obj, key):
        """Return the actual attribute name on obj matching key case-insensitively, or None."""
        if hasattr(obj, key):
            return key
        key_lower = key.lower()
        source = obj.to_dict() if hasattr(obj, "to_dict") else {}
        for actual in source:
            if not actual.startswith("_") and actual.lower() == key_lower:
                return actual
        return None

    def get_chunk(self, chunk=None):
        """Return config value(s) for a dotted chunk path, or full config if None."""
        obj = self.rizza
        if chunk is None:
            return obj.to_dict() if hasattr(obj, "to_dict") else obj
        for key in chunk.split("."):
            actual = self._resolve_attr_key(obj, key)
            if actual is None:
                raise KeyError(f"Config key not found: {chunk!r}")
            obj = getattr(obj, actual)
        return obj.to_dict() if hasattr(obj, "to_dict") else obj

    def set_chunk(self, chunk, value):
        """Set a config value by dotted chunk path and persist to the appropriate file."""
        coerced = yaml.safe_load(str(value))
        keys = chunk.split(".")
        obj = self.rizza
        for key in keys[:-1]:
            actual = self._resolve_attr_key(obj, key)
            if actual is None:
                raise KeyError(f"Config key not found: {chunk!r}")
            obj = getattr(obj, actual)
        leaf = self._resolve_attr_key(obj, keys[-1])
        if leaf is None:
            raise KeyError(f"Config key not found: {chunk!r}")
        setattr(obj, leaf, coerced)
        self._write_chunk_to_file(chunk)

    def _resolve_file_for_chunk(self, chunk):
        """Return the .pconf file path that owns the given chunk."""
        top = chunk.split(".")[0]
        filename = IMPORTED_CHUNKS.get(top, "rizza.pconf")
        return Path(self.cfg_dir) / filename

    def _write_chunk_to_file(self, chunk):
        """Persist the in-memory section owning chunk back to its .pconf file."""
        top = chunk.split(".")[0]
        target = self._resolve_file_for_chunk(chunk)
        target.parent.mkdir(parents=True, exist_ok=True)

        if top in IMPORTED_CHUNKS:
            section = getattr(self.rizza, top)
            data = section.to_dict() if hasattr(section, "to_dict") else section
        else:
            full = self.rizza.to_dict() if hasattr(self.rizza, "to_dict") else dict(self.rizza)
            data = {k: v for k, v in full.items() if k not in IMPORTED_CHUNKS}
            data["_import"] = [v for v in IMPORTED_CHUNKS.values()]

        target.write_text(yaml.dump(data, default_flow_style=False))

    def init_config(self, force=False, chunk=None):
        """Copy .pconf.example files from the project config/ dir to ~/rizza/config/.

        If chunk is given (one of 'rizza', 'genetics', 'connection'), only that
        file is copied; otherwise all example files are copied.
        """
        chunk_map = {"rizza": "rizza.pconf", **IMPORTED_CHUNKS}
        src_dir = Path(__file__).parent.parent.parent / "config"
        dest_dir = Path(self.cfg_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        skipped = []
        if chunk:
            target = chunk_map[chunk]
            examples = [src_dir / f"{target}.example"]
        else:
            examples = list(src_dir.glob("*.pconf.example"))
        for example in examples:
            dest = dest_dir / example.name.removesuffix(".example")
            if not example.exists() or (dest.exists() and not force):
                skipped.append(dest.name)
            else:
                shutil.copy2(example, dest)
                copied.append(dest.name)
        rizza_pconf = dest_dir / "rizza.pconf"
        if rizza_pconf.exists():
            self.rizza = PicoConf(str(rizza_pconf))
        return {"copied": copied, "skipped": skipped}

    @property
    def product_version_minor(self):
        """Return the major.minor version string, or 'stream' if unset."""
        v = getattr(self.rizza, "product_version", "")
        return _version_minor(v) if v else "stream"

    @property
    def product_slug(self):
        """Return '{product_name}-{major.minor}' for directory naming."""
        name = getattr(self.rizza, "product_name", "satellite")
        return f"{name}-{self.product_version_minor}"

    @property
    def genetic_tests_dir(self):
        """Return the data directory for genetic tests, namespaced by product-version/interface."""
        interface = getattr(self.rizza, "interface", "api")
        return self.base_dir / "data" / "genetic_tests" / self.product_slug / interface

    def genetic_tests_dir_for_version(self, version):
        """Return the genetic tests directory for an arbitrary version."""
        interface = getattr(self.rizza, "interface", "api")
        name = getattr(self.rizza, "product_name", "satellite")
        slug = f"{name}-{_version_minor(version)}"
        return self.base_dir / "data" / "genetic_tests" / slug / interface

    def _checkpoint_path(self):
        """Return the checkpoint file path for the current product-version and interface."""
        interface = getattr(self.rizza, "interface", "api")
        return self.base_dir / "data" / f"explore_checkpoint_{self.product_slug}_{interface}"

    def save_checkpoint(self, entity: str, method: str):
        """Write the current exploration position to the interface-specific checkpoint."""
        checkpoint = self._checkpoint_path()
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(f"{entity}::{method}")

    def load_checkpoint(self) -> "tuple[str, str] | tuple[None, None]":
        """Read the last exploration checkpoint, returning (entity, method) or (None, None)."""
        checkpoint = self._checkpoint_path()
        if not checkpoint.exists():
            return None, None
        text = checkpoint.read_text().strip()
        if "::" in text:
            entity, method = text.split("::", 1)
            return entity or None, method or None
        return None, None

    @staticmethod
    def yaml_print(in_dict=None):
        """Convert a dictionary to yaml string, and print it out"""
        if in_dict is not None:
            out = in_dict.to_dict() if hasattr(in_dict, "to_dict") else in_dict
            print(yaml.dump(out, default_flow_style=False))
        else:
            print("Configuration dictionary is None.")
