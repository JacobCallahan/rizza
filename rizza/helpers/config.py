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

DEFAULT_CONFIG = {
    "genetics": {
        "population_count": 100,
        "max_generations": 10000,
        "allow_dependencies": True,
        "allow_recursion": True,
        "max_recursive_generations": 10000,
        "max_recursive_depth": 10,
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
    },
    "connection": {
        "hostname": "",
        "username": "admin",
        "password": "changeme",
    },
    "apix_lib_path": "~/rizza/apix_generated.py",
    "log_path": "logs/rizza.log",
    "log_level": "info",
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
        if "project" in dir(args):
            if args.project == "rizza" and not args.show and not args.clear:
                logger.debug("Set rizza configuration.")
        elif command:
            self.rizza.last = {k: v for k, v in vars(args).items() if not k.startswith("_")}
            self.save_config()
            logger.debug("Command arguments saved to last.pconf")

    def save_config(self, cfg_file=None):
        """Save the LAST command arguments to last.pconf in the config directory."""
        last_data = getattr(self.rizza, "last", None)
        if last_data is None:
            return

        last_dir = Path(cfg_file).parent if cfg_file else Path(self.cfg_dir)
        last_file = last_dir / "last.pconf"
        last_dir.mkdir(parents=True, exist_ok=True)

        last_dict = last_data.to_dict() if hasattr(last_data, "to_dict") else last_data
        yaml_str = yaml.dump({"last": last_dict}, default_flow_style=False)
        last_file.write_text(yaml_str)

        logger.info(f"Saved last configuration to: {last_file}")

    def init_connection(self):
        """Initialize the apix API connection using connection config values."""
        from rizza import apix_loader

        conn = self.rizza.connection
        hostname = conn.hostname
        username = conn.username
        password = conn.password

        apix_loader.get_apix_module(path=self.rizza.apix_lib_path)

        APIConnection = apix_loader.get_connection_class()
        APIConnection(hostname=hostname, auth=f"{username}:{password}")
        logger.debug(f"API connection initialized for host: {hostname}")

    def init_logger(self, path=None, level=None):
        path = path or self.rizza.log_path
        level = level or self.rizza.log_level
        setup_logging(console_level=level, file_level=level, log_path=path)

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

    def init_config(self, force=False):
        """Copy .pconf.example files from the project config/ dir to ~/rizza/config/."""
        src_dir = Path(__file__).parent.parent.parent / "config"
        dest_dir = Path(self.cfg_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        skipped = []
        for example in src_dir.glob("*.pconf.example"):
            dest = dest_dir / example.name.removesuffix(".example")
            if dest.exists() and not force:
                skipped.append(dest.name)
            else:
                shutil.copy2(example, dest)
                copied.append(dest.name)
        rizza_pconf = dest_dir / "rizza.pconf"
        if rizza_pconf.exists():
            self.rizza = PicoConf(str(rizza_pconf))
        return {"copied": copied, "skipped": skipped}

    @staticmethod
    def yaml_print(in_dict=None):
        """Convert a dictionary to yaml string, and print it out"""
        if in_dict is not None:
            out = in_dict.to_dict() if hasattr(in_dict, "to_dict") else in_dict
            print(yaml.dump(out, default_flow_style=False))
        else:
            print("Configuration dictionary is None.")
