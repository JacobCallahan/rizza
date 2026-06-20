"""Project configuration helpers."""
from copy import deepcopy
from pathlib import Path

import attr
from logzero import logger
from picoconf import PicoConf
import yaml

from rizza.helpers import logger as rza_logger


def conf_to_dict(obj):
    """Recursively convert PicoConf objects to plain dictionaries."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: conf_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [conf_to_dict(item) for item in obj]
    return obj


# Default configuration values
DEFAULT_CONFIG = {
    "GENETICS": {
        "POPULATION COUNT": 100,
        "MAX GENERATIONS": 10000,
        "ALLOW DEPENDENCIES": True,
        "ALLOW RECURSION": True,
        "MAX RECURSIVE GENERATIONS": 10000,
        "MAX RECURSIVE DEPTH": 10,
        "CRITERIA": {
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
        }
    },
    "LOG PATH": "logs/rizza.log",
    "LOG LEVEL": "info"
}


@attr.s()
class Config:
    """Encompassing configuration class.

    Order of preference is:
        1. CLI Arguments
        2. Environmental Variables
        3. Configuration File(s)
    """

    cfg_file = attr.ib(default="config/rizza.pconf", cmp=False, repr=False)
    RIZZA = attr.ib(default=attr.Factory(dict), cmp=False)

    def __attrs_post_init__(self):
        """Load in config files, then environment variables"""
        self.base_dir = Path.home().joinpath("rizza")
        # we want to always use current directory as base for tests
        if "tests" in str(self.cfg_file):
            self.cfg_file = Path().joinpath(self.cfg_file)
        elif self.cfg_file != str(Path(self.cfg_file).absolute()):
            self.cfg_file = self.base_dir.joinpath(self.cfg_file)
        self.load_config()
        self.RIZZA.CONFILE = str(self.cfg_file)
        self._load_environment_vars()

    def _load_environment_vars(self):
        """Load in key variables that may exist in the environment"""
        pass  # Nailgun related environment variables removed

    def _load_defaults(self):
        """Ensure default configuration values are populated."""
        if not isinstance(self.RIZZA, PicoConf):
            self.RIZZA = PicoConf(self.RIZZA if isinstance(self.RIZZA, dict) else {})

        for key, value in DEFAULT_CONFIG.items():
            current_value = self.RIZZA.get(key)
            if current_value is None:
                self.RIZZA[key] = deepcopy(value)
            elif isinstance(value, dict) and isinstance(current_value, (dict, PicoConf)):
                for sub_key, sub_value in value.items():
                    if current_value.get(sub_key) is None:
                        current_value[sub_key] = deepcopy(sub_value)

    def load_config(self, cfg_file=None):
        """Load configuration using picoconf only."""
        infile = Path(cfg_file or self.cfg_file).resolve()
        logger.info(f"Loading config from {infile.absolute()}")

        if infile.suffix != ".pconf":
            infile = infile.with_suffix(".pconf")

        try:
            if infile.exists():
                pico_config = PicoConf(str(infile))
                if "RIZZA" in pico_config:
                    self.RIZZA = PicoConf(conf_to_dict(pico_config["RIZZA"]))
                elif "rizza" in pico_config:
                    self.RIZZA = PicoConf(conf_to_dict(pico_config["rizza"]))
                else:
                    self.RIZZA = pico_config
            else:
                logger.warning(f"Config file {infile.absolute()} not found. Using defaults.")
                self.RIZZA = PicoConf({})
        except Exception as e:
            logger.error(f"Error loading config file {infile.absolute()}: {e}. Using defaults.")
            self.RIZZA = PicoConf({})

        self._load_defaults()
        log_path = self.RIZZA.get("LOG PATH", DEFAULT_CONFIG["LOG PATH"])
        if log_path != str(Path(log_path).absolute()):
            self.RIZZA["LOG PATH"] = str(self.base_dir.joinpath(log_path))
        self.RIZZA.LOG_PATH = self.RIZZA["LOG PATH"]
        self.RIZZA.LOG_LEVEL = self.RIZZA.get("LOG LEVEL", DEFAULT_CONFIG["LOG LEVEL"])

    def load_cli_args(self, args=None, command=False):  # (too many branches)
        """Pull in any relevant settings from argparse"""
        if "project" in dir(args):
            if args.project == "rizza":
                if args.path:
                    self.RIZZA.CONFILE = args.path
                if not args.show and not args.clear:
                    self.save_config()
                    logger.debug("Set rizza configuration.")
        elif command:
            # If we are pulling in args from a command, save them for future use
            self.RIZZA.LAST = vars(args)
            self.save_config()
            logger.debug(f"Command arguments saved in: {self.RIZZA.get('CONFILE', 'unknown')}")

    def save_config(self, cfg_file=None):
        """Save the current configuration to a pconf file."""
        outfile = Path(cfg_file or self.cfg_file)
        if outfile.suffix != ".pconf":
            outfile = outfile.with_suffix(".pconf")

        rizza_dict = conf_to_dict(self.RIZZA)

        with outfile.open("w") as cfg_dump:
            yaml.dump(rizza_dict, cfg_dump, default_flow_style=False)

        logger.info(f"Saved current configuration in: {outfile}")

    def init_logger(self, path=None, level=None):
        path = path or self.RIZZA.get("LOG PATH", "logs/rizza.log")
        level = level or self.RIZZA.get("LOG LEVEL", "info")
        rza_logger.setup_logzero(path, level)

    def clear_rizza(self):
        """Clear all current rizza configurations"""
        self.RIZZA = PicoConf({})
        self.save_config()

    @staticmethod
    def yaml_print(in_dict=None):
        """Convert a dictionary to yaml string, and print it out"""
        # rprint(Syntax(yaml_string, "yaml", theme="native", line_numbers=True))
        # For consistency with potential prior usage if rprint not available:
        if in_dict is not None:
            print(yaml.dump(in_dict, default_flow_style=False))
        else:
            print("Configuration dictionary is None.")
