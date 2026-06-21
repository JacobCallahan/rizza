"""Project configuration helpers."""
from pathlib import Path

import attr
from logzero import logger
from picoconf import PicoConf
import yaml

from rizza.helpers import logger as rza_logger

# Default configuration values - nested under "rizza" to match directory loading.
# These are used as construction-time defaults; .pconf files in the config directory
# take precedence when present.
DEFAULT_CONFIG = {
    "rizza": {
        "GENETICS": {
            "POPULATION_COUNT": 100,
            "MAX_GENERATIONS": 10000,
            "ALLOW_DEPENDENCIES": True,
            "ALLOW_RECURSION": True,
            "MAX_RECURSIVE_GENERATIONS": 10000,
            "MAX_RECURSIVE_DEPTH": 10,
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
            },
        },
        "LOG_PATH": "logs/rizza.log",
        "LOG_LEVEL": "info",
    }
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
    RIZZA = attr.ib(default=attr.Factory(dict), cmp=False)

    def __attrs_post_init__(self):
        """Load configuration from a directory of .pconf files using picoconf."""
        self.base_dir = Path.home().joinpath("rizza")
        if "tests" in str(self.cfg_dir):
            self.cfg_dir = Path().joinpath(self.cfg_dir)
        elif self.cfg_dir != str(Path(self.cfg_dir).absolute()):
            self.cfg_dir = self.base_dir.joinpath(self.cfg_dir)

        config = PicoConf(str(self.cfg_dir), **DEFAULT_CONFIG)
        self.RIZZA = (
            config.rizza if hasattr(config, "rizza") else PicoConf(DEFAULT_CONFIG["rizza"])
        )

    def load_cli_args(self, args=None, command=False):
        """Pull in any relevant settings from argparse"""
        if "project" in dir(args):
            if args.project == "rizza" and not args.show and not args.clear:
                logger.debug("Set rizza configuration.")
        elif command:
            self.RIZZA.LAST = vars(args)
            self.save_config()
            logger.debug("Command arguments saved to last.pconf")

    def save_config(self, cfg_file=None):
        """Save the LAST command arguments to last.pconf in the config directory."""
        last_data = self.RIZZA.get("LAST")
        if last_data is None:
            return

        last_dir = Path(cfg_file).parent if cfg_file else Path(self.cfg_dir)
        last_file = last_dir / "last.pconf"
        last_dir.mkdir(parents=True, exist_ok=True)

        last_dict = last_data.to_dict() if hasattr(last_data, "to_dict") else last_data
        with last_file.open("w") as f:
            yaml.dump({"LAST": last_dict}, f, default_flow_style=False)

        logger.info(f"Saved last configuration to: {last_file}")

    def init_logger(self, path=None, level=None):
        path = path or self.RIZZA.get("LOG_PATH", DEFAULT_CONFIG["rizza"]["LOG_PATH"])
        level = level or self.RIZZA.get("LOG_LEVEL", DEFAULT_CONFIG["rizza"]["LOG_LEVEL"])
        rza_logger.setup_logzero(path, level)

    def clear_rizza(self):
        """Reset rizza configuration to defaults in memory.

        Note: This does not write to disk. The on-disk .pconf files are not
        modified; only the in-memory configuration is reset to DEFAULT_CONFIG.
        """
        self.RIZZA = PicoConf(DEFAULT_CONFIG["rizza"])

    @staticmethod
    def yaml_print(in_dict=None):
        """Convert a dictionary to yaml string, and print it out"""
        if in_dict is not None:
            out = in_dict.to_dict() if hasattr(in_dict, "to_dict") else in_dict
            print(yaml.dump(out, default_flow_style=False))
        else:
            print("Configuration dictionary is None.")
