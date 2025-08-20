"""Project configuration helpers."""
from pathlib import Path

import attr
from logzero import logger
from nanoconf import NanoConf
import yaml

from rizza.helpers import logger as rza_logger


def box_to_dict(obj):
    """Recursively convert Box objects to plain dictionaries"""
    if hasattr(obj, '_box_config') or (hasattr(obj, 'to_dict') and hasattr(obj, 'keys')):
        # This is likely a Box object
        return {k: box_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, dict):
        return {k: box_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [box_to_dict(item) for item in obj]
    else:
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


# Patch NanoConf to add missing functionality
def to_dict(self):
    """Convert NanoConf instance to a dictionary, excluding internal attributes"""
    result = {}
    for key, value in self.__dict__.items():
        # Skip private/internal attributes and methods
        if not key.startswith('_') and not callable(value):
            try:
                # Try to convert complex objects to simple types
                if hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, list, dict)):
                    # This is a complex object, try to convert recursively
                    if hasattr(value, 'to_dict'):
                        result[key] = value.to_dict()
                    else:
                        # Skip complex objects that can't be converted
                        continue
                else:
                    result[key] = value
            except (TypeError, AttributeError):
                # Skip attributes that can't be serialized
                continue
    return result

# Add the to_dict method to NanoConf at runtime
NanoConf.to_dict = to_dict


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
        
        # Initialize RIZZA as dict first, then load config
        self.load_config()
        
        # Set CONFILE after loading
        setattr(self.RIZZA, 'CONFILE', str(self.cfg_file))
        self._load_environment_vars()

    def _load_environment_vars(self):
        """Load in key variables that may exist in the environment"""
        pass  # Nailgun related environment variables removed

    def _load_defaults(self):
        """Ensure default configuration values are populated."""
        # If RIZZA is not a NanoConf instance, convert it
        if not isinstance(self.RIZZA, NanoConf):
            self.RIZZA = NanoConf(self.RIZZA if isinstance(self.RIZZA, dict) else {})
        
        # Apply defaults from DEFAULT_CONFIG
        for key, value in DEFAULT_CONFIG.items():
            key_attr = key.replace(' ', '_').upper()
            current_value = getattr(self.RIZZA, key_attr, None)
            if current_value is None:
                setattr(self.RIZZA, key_attr, value)
            elif isinstance(value, dict) and hasattr(current_value, '__dict__'):
                # For nested dicts like GENETICS, merge missing keys
                for sub_key, sub_value in value.items():
                    sub_key_attr = sub_key.replace(' ', '_').upper()
                    if not hasattr(current_value, sub_key_attr) or getattr(current_value, sub_key_attr, None) is None:
                        setattr(current_value, sub_key_attr, sub_value)

    def load_config(self, cfg_file=None):
        """Load configuration using nanoconf only"""
        infile = Path(cfg_file or self.cfg_file).resolve()
        logger.info(f"Loading config from {infile.absolute()}")

        # Convert to .nconf if needed
        if not str(infile).endswith('.nconf'):
            infile = infile.with_suffix('.nconf')

        try:
            if infile.exists():
                # Load the nanoconf
                nano_config = NanoConf(str(infile))
                
                # Check if we have rizza config - either direct content or under RIZZA key
                if hasattr(nano_config, 'RIZZA'):
                    # Config saved with RIZZA key (from save_config method)
                    # Get the raw dict data instead of Box object to avoid serialization issues
                    rizza_data = getattr(nano_config, 'RIZZA')
                    
                    # Convert Box objects to plain dictionaries recursively
                    rizza_dict = box_to_dict(rizza_data)
                    
                    # Create a temp file to create NanoConf from the dict
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.nconf', delete=False) as f:
                        yaml.dump(rizza_dict, f, default_flow_style=False)
                        temp_path = f.name
                    self.RIZZA = NanoConf(temp_path)
                    Path(temp_path).unlink()  # Clean up temp file
                elif infile.name.startswith('rizza') or infile.name.startswith('test_config'):
                    # This is a rizza config file - use its content directly
                    self.RIZZA = nano_config
                else:
                    # Look for rizza attribute or initialize empty
                    if hasattr(nano_config, 'rizza'):
                        self.RIZZA = nano_config.rizza
                    else:
                        # Initialize empty by creating a temp nconf file with empty dict content
                        import tempfile
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.nconf', delete=False) as f:
                            print('{}', file=f)
                            temp_path = f.name
                        self.RIZZA = NanoConf(temp_path)
                        Path(temp_path).unlink()  # Clean up temp file
            else:
                logger.warning(f"Config file {infile.absolute()} not found. Using defaults.")
                # Initialize empty by creating a temp nconf file with empty dict content
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.nconf', delete=False) as f:
                    print('{}', file=f)
                    temp_path = f.name
                self.RIZZA = NanoConf(temp_path)
                Path(temp_path).unlink()  # Clean up temp file
        except Exception as e:
            logger.error(f"Error loading config file {infile.absolute()}: {e}. Using defaults.")
            # Initialize empty by creating a temp nconf file with empty dict content
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.nconf', delete=False) as f:
                print('{}', file=f)
                temp_path = f.name
            self.RIZZA = NanoConf(temp_path)
            Path(temp_path).unlink()  # Clean up temp file

        # Apply default values
        self._load_defaults()
        
        # Set up logging paths
        log_path = getattr(self.RIZZA, 'LOG_PATH', DEFAULT_CONFIG['LOG PATH'])
        if log_path != str(Path(log_path).absolute()):
            setattr(self.RIZZA, 'LOG_PATH', str(self.base_dir.joinpath(log_path)))

    def load_cli_args(self, args=None, command=False):  # (too many branches)
        """Pull in any relevant settings from argparse"""
        if "project" in dir(args):
            if args.project == "rizza":
                if args.path:
                    setattr(self.RIZZA, 'CONFILE', args.path)
                if not args.show and not args.clear:
                    self.save_config()
                    logger.debug("Set rizza configuration.")
        elif command:
            # If we are pulling in args from a command, save them for future use
            setattr(self.RIZZA, 'LAST', vars(args))
            self.save_config()
            logger.debug("Command arguments saved in: {}".format(getattr(self.RIZZA, 'CONFILE', 'unknown')))

    def save_config(self, cfg_file=None):
        """Save the current configuration to a nconf file"""
        # Include any non-serializable objects that can't be saved.
        outfile = Path(cfg_file or self.cfg_file)
        
        # Always save as .nconf format
        if not str(outfile).endswith('.nconf'):
            outfile = outfile.with_suffix('.nconf')
            
        # Use this list to remove entire class variables
        exclude_list = ["base_dir", "cfg_file"]
        
        # Convert RIZZA NanoConf to dictionary for saving
        rizza_dict = {}
        if hasattr(self.RIZZA, 'to_dict'):
            rizza_dict = self.RIZZA.to_dict()
        else:
            # Fallback: extract non-private attributes manually and safely
            for attr_name in dir(self.RIZZA):
                if not attr_name.startswith('_') and not callable(getattr(self.RIZZA, attr_name)):
                    try:
                        value = getattr(self.RIZZA, attr_name)
                        rizza_dict[attr_name] = value
                    except (TypeError, AttributeError):
                        # Skip problematic attributes
                        continue
        
        # Convert all Box objects to plain dictionaries recursively
        rizza_dict = box_to_dict(rizza_dict)

        with outfile.open("w") as cfg_dump:
            # Create output dictionary with just the RIZZA data
            out_dict = {"RIZZA": rizza_dict}
            # Always save as YAML format (which nanoconf uses)
            yaml.dump(out_dict, cfg_dump, default_flow_style=False)

        logger.info(f"Saved current configuration in: {outfile}")

    def init_logger(self, path=None, level=None):
        path = path or getattr(self.RIZZA, 'LOG_PATH', 'logs/rizza.log')
        level = level or getattr(self.RIZZA, 'LOG_LEVEL', 'info')
        rza_logger.setup_logzero(path, level)

    def clear_rizza(self):
        """Clear all current rizza configurations"""
        # Initialize empty by creating a temp nconf file with empty dict content
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.nconf', delete=False) as f:
            print('{}', file=f)
            temp_path = f.name
        self.RIZZA = NanoConf(temp_path)
        Path(temp_path).unlink()  # Clean up temp file
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
