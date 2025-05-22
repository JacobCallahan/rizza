"""Project configuration helpers."""
import json
import os
from pathlib import Path

import attr
from logzero import logger
import yaml

from rizza.helpers import logger as rza_logger
from rizza.helpers.misc import json_serial


@attr.s()
class Config:
    """Encompassing configuration class.

    Order of preference is:
        1. CLI Arguments
        2. Environmental Variables
        3. Configuration File(s)
    """

    cfg_file = attr.ib(default="config/rizza.yaml", cmp=False, repr=False)
    RIZZA = attr.ib(default=attr.Factory(dict), cmp=False)

    def __attrs_post_init__(self):
        """Load in config files, then environment variables"""
        self.base_dir = Path.home().joinpath("rizza")
        # we want to always use current directory as base for tests
        if "tests" in str(self.cfg_file):
            self.cfg_file = Path().joinpath(self.cfg_file)
        elif self.cfg_file != str(Path(self.cfg_file).absolute()):
            self.cfg_file = self.base_dir.joinpath(self.cfg_file)
        self.RIZZA["CONFILE"] = self.cfg_file
        self.load_config()
        self._load_environment_vars()

    def _load_environment_vars(self):
        """Load in key variables that may exist in the environment"""
        pass # Nailgun related environment variables removed

    def _load_genetics(self):
        """Ensure the genetic algorithm vars are populated."""
        if not self.RIZZA.get("GENETICS", None):
            # No configuration found. Begin creating one.
            self.RIZZA["GENETICS"] = {}
        if not self.RIZZA["GENETICS"].get("POPULATION COUNT"):
            self.RIZZA["GENETICS"]["POPULATION COUNT"] = 100
        if not self.RIZZA["GENETICS"].get("MAX GENERATIONS"):
            self.RIZZA["GENETICS"]["MAX GENERATIONS"] = 10000
        if self.RIZZA["GENETICS"].get("ALLOW DEPENDENCIES", "x") == "x":
            self.RIZZA["GENETICS"]["ALLOW DEPENDENCIES"] = True
        if self.RIZZA["GENETICS"].get("ALLOW RECURSION", "x") == "x":
            self.RIZZA["GENETICS"]["ALLOW RECURSION"] = True
        if not self.RIZZA["GENETICS"].get("MAX RECURSIVE GENERATIONS"):
            self.RIZZA["GENETICS"]["MAX RECURSIVE GENERATIONS"] = 10000
        if not self.RIZZA["GENETICS"].get("MAX RECURSIVE DEPTH"):
            self.RIZZA["GENETICS"]["MAX RECURSIVE DEPTH"] = 10
        if not self.RIZZA["GENETICS"].get("CRITERIA"):
            self.RIZZA["GENETICS"]["CRITERIA"] = {
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

    def load_config(self, cfg_file=None):
        """Attempt to load in config files"""
        infile = Path(cfg_file or self.cfg_file).resolve()
        logger.info(f"Loading config from {infile.absolute()}")
        loaded_cfg = {} # Default to empty config
        try:
            if infile.exists():
                if infile.suffix == ".json":
                    loaded_cfg = json.loads(infile.read_text())
                elif infile.suffix in [".yml", ".yaml"]:
                    loaded_cfg = yaml.load(infile.read_text(), Loader=yaml.FullLoader)
            else:
                logger.warning(f"Configuration file {infile.absolute()} not found. Using default/empty config.")
        except FileNotFoundError:
            logger.warning(f"Configuration file {infile.absolute()} not found (FileNotFoundError). Using default/empty config.")
        except Exception as e:
            logger.error(f"Error loading configuration file {infile.absolute()}: {e}. Using default/empty config.")

        if "RIZZA" in loaded_cfg:
            self.RIZZA = loaded_cfg["RIZZA"]
            self._load_genetics()
            self.RIZZA["LOG PATH"] = self.RIZZA.get("LOG PATH", "logs/rizza.log")
            if self.RIZZA["LOG PATH"] != str(Path(self.RIZZA["LOG PATH"]).absolute()):
                self.RIZZA["LOG PATH"] = self.base_dir.joinpath(self.RIZZA["LOG PATH"])
            self.RIZZA["LOG LEVEL"] = self.RIZZA.get("LOG LEVEL", "info")

    def load_cli_args(self, args=None, command=False):  # noqa: PLR0912 (too many branches)
        """Pull in any relevant settings from argparse"""
        if "project" in dir(args):
            if args.project == "rizza":
                if args.path:
                    self.RIZZA["CONFILE"] = args.path
                if not args.show and not args.clear:
                    self.save_config()
                    logger.debug("Set rizza configuration.")
        elif command:
            # If we are pulling in args from a command, save them for future use
            self.RIZZA["LAST"] = vars(args)
            self.save_config()
            logger.debug("Command arguments saved in: {}".format(self.RIZZA["CONFILE"]))

    def save_config(self, cfg_file=None):
        """Save the current configuration to a yaml or json file"""
        # Include any non-serializable objects that can't be saved.
        outfile = Path(cfg_file or self.cfg_file)
        # Use this list to remove entire class variables
        exclude_list = ["base_dir", "cfg_file"]
        # Use this list to remove unserializable objects
        sanitized = [] # Nailgun related sanitization removed
        # Remove each of those objects
        for item in sanitized:
            # This block might need adjustment if NAILGUN was a direct attribute vs. a dict key
            if item["component"] in self.__dict__ and isinstance(self.__dict__[item["component"]], dict) and \
               self.__dict__[item["component"]].get(item["name"], None):
                del self.__dict__[item["component"]][item["name"]]
            elif hasattr(self, item["component"]) and isinstance(getattr(self, item["component"]), dict) and \
                 getattr(self, item["component"]).get(item["name"], None): 
                 del getattr(self, item["component"])[item["name"]]


        with outfile.open("w") as cfg_dump:
            filter_func = lambda attr, value: attr.name not in exclude_list
            out_dict = attr.asdict(self, filter=filter_func)
            if ".json" in str(outfile):
                json.dump(out_dict, cfg_dump, indent=4, default=json_serial)
            elif ".yml" in str(outfile) or ".yaml" in str(outfile):
                yaml.dump(out_dict, cfg_dump, default_flow_style=False)

        logger.info(f"Saved current configuration in: {outfile}")
        # Add back in the sanitized items
        for item in sanitized:
            # This block might need adjustment
            if item["component"] in self.__dict__ and isinstance(self.__dict__[item["component"]], dict):
                 self.__dict__[item["component"]][item["name"]] = item["contents"]
            elif hasattr(self, item["component"]) and isinstance(getattr(self, item["component"]), dict):
                 getattr(self, item["component"])[item["name"]] = item["contents"]

    def init_logger(self, path=None, level=None):
        path = path or self.RIZZA["LOG PATH"]
        level = level or self.RIZZA["LOG LEVEL"]
        rza_logger.setup_logzero(path, level)

    def clear_rizza(self):
        """Clear all current rizza configurations"""
        self.RIZZA = {}
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
