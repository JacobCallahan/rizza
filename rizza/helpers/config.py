# -*- encoding: utf-8 -*-
"""Project configuration helpers."""
import json
import os
import yaml
import attr
from nailgun.config import ServerConfig


@attr.s()
class Config():
    """Encompassing configuration class.

    Order of preference is:
        1. CLI Arguments
        2. Environmental Variables
        3. Configuration File(s)
    """

    cfg_file = attr.ib(default='config/rizza.yaml', cmp=False, repr=False)
    RIZZA = attr.ib(default=attr.Factory(dict), cmp=False)
    NAILGUN = attr.ib(default=attr.Factory(dict), cmp=False)

    def __attrs_post_init__(self):
        """Load in config files, then environment variables"""
        # first, attempt to load nailgun config
        self.RIZZA['CONFILE'] = self.cfg_file
        self.load_config()
        self._load_environment_vars()

    def _load_environment_vars(self):
        """Load in key variables that may exist in the environment"""
        self.NAILGUN['SATHOST'] = os.environ.get(
            'SATHOST', self.NAILGUN.get('SATHOST', 'https://localhost'))
        self.NAILGUN['SATUSER'] = os.environ.get(
            'SATUSER', self.NAILGUN.get('SATUSER', 'admin'))
        self.NAILGUN['SATPASS'] = os.environ.get(
            'SATPASS', self.NAILGUN.get('SATPASS', 'changeme'))
        self.NAILGUN['CONFILE'] = os.environ.get(
            'CONFILE', self.NAILGUN.get('CONFILE', None))

    def _load_nailgun(self, path=None):
        """Check if there is an auto-loadable json config."""
        try:
            server_config = ServerConfig(url='').get(path=path)
        except:
            try:
                server_config = ServerConfig(url='').get(
                    path='config/server_configs.json')
                server_config.save()
            except Exception as e:
                pass
        self.nailgun_config(conf=server_config)

    def _load_genetics(self):
        """Ensure the genetic algorithm vars are populated."""
        if not self.RIZZA.get('GENETICS', None):
            # No configuration found. Begin creating one.
            self.RIZZA['GENETICS'] = {}
        if not self.RIZZA['GENETICS'].get('POPULATION COUNT'):
            self.RIZZA['GENETICS']['POPULATION COUNT'] = 100
        if not self.RIZZA['GENETICS'].get('MAX GENERATIONS'):
            self.RIZZA['GENETICS']['MAX GENERATIONS'] = 10000
        if not self.RIZZA['GENETICS'].get('ALLOW RECURSION'):
            self.RIZZA['GENETICS']['ALLOW RECURSION'] = True
        if not self.RIZZA['GENETICS'].get('MAX RECURSIVE GENERATIONS'):
            self.RIZZA['GENETICS']['MAX RECURSIVE GENERATIONS'] = 10000
        if not self.RIZZA['GENETICS'].get('MAX RECURSIVE DEPTH'):
            self.RIZZA['GENETICS']['MAX RECURSIVE DEPTH'] = 10
        if not self.RIZZA['GENETICS'].get('CRITERIA'):
            self.RIZZA['GENETICS']['CRITERIA'] = {
                'pass': 500,
                'fail': -200,
                'HTTPError': -200,
                '200': 1000,
                '404': -500,
                '422': -200,
                '500': -1000,
                'created': 500,
                'BadValueError': -500,
                'TypeError': -200
            }

    def load_config(self, cfg_file=None):
        """Attempt to load in config files"""
        infile = cfg_file or self.RIZZA['CONFILE']
        with open(infile) as tempf:
            if '.json' in infile:
                try:
                    loaded_cfg = json.load(tempf)
                except Exception as e:
                    print(e)
            elif '.yml' in infile or '.yaml' in infile:
                try:
                    loaded_cfg = yaml.load(tempf)
                except Exception as e:
                    print(e)

        if 'NAILGUN' in loaded_cfg:
            self.NAILGUN = loaded_cfg['NAILGUN']
            self.nailgun_config()
        else:
            self._load_nailgun()
        if 'RIZZA' in loaded_cfg:
            self.RIZZA = loaded_cfg['RIZZA']
            self._load_genetics()

    def load_cli_args(self, args=None, command=False):
        """Pull in any relevant settings from argparse"""
        if 'project' in dir(args):
            if args.project == 'nailgun':
                if args.target:
                    self.NAILGUN['SATHOST'] = args.target
                if args.user:
                    self.NAILGUN['SATUSER'] = args.user
                if args.password:
                    self.NAILGUN['SATPASS'] = args.password
                if args.verify:
                    self.NAILGUN['VERIFY'] = args.verify
                if args.label:
                    self.NAILGUN['LABEL'] = args.verify
                if args.path:
                    self.NAILGUN['CONFILE'] = args.path
                    self._load_nailgun(path=args.path)
                if not args.show and not args.clear:
                    self.save_config()
                    print('Set nailgun configuration.')
            elif args.project == 'rizza':
                if args.path:
                    self.RIZZA['CONFILE'] = args.path
                if not args.show and not args.clear:
                    self.save_config()
                    print('Set rizza configuration.')
        elif command:
            # If we are pulling in args from a command, save them for future use
            self.RIZZA['LAST'] = vars(args)
            self.save_config()
            print('Command arguments saved in: {}'.format(self.RIZZA['CONFILE']))

    def save_config(self, cfg_file=None):
        """Save the current configuration to a yaml or json file"""
        # Include any non-serializable objects that can't be saved.
        outfile = cfg_file or self.RIZZA.get('CONFILE', self.cfg_file)
        # Use this list to remove entire class variables
        exclude_list = ['cfg_file']
        # Use this list to remove unserializable objects
        sanitized = [{
            'component': 'NAILGUN', 'name': 'CONFIG',
            'contents': self.NAILGUN.get('CONFIG', '')
        }]
        # Remove each of those objects
        for item in sanitized:
            if self.__dict__[item['component']].get(item['name'], None):
                del self.__dict__[item['component']][item['name']]

        with open(outfile, 'w') as cfg_dump:
            out_dict = attr.asdict(self,
                filter=lambda attr, value: attr.name not in exclude_list)
            if '.json' in outfile:
                json.dump(out_dict, cfg_dump, indent=4)
            elif '.yml' in outfile or '.yaml' in outfile:
                yaml.dump(out_dict, cfg_dump, default_flow_style=False)

        print('Saved current configuration in: {}'.format(outfile))
        # Add back in the sanitized items
        for item in sanitized:
            self.__dict__[item['component']][item['name']] = item['contents']

    def nailgun_config(self, conf=None, label='default'):
        """Return the current nailgun config.
        If a new one is passed in, save it and parse the pieces.
        If one isn't passed in and doesn't currently exist, create it.
        """
        if conf:
            # Load the passed in configuration file
            self.NAILGUN['CONFIG'] = conf
            self.NAILGUN['SATHOST'] = conf.url or os.uname()[1]
            self.NAILGUN['SATUSER'], self.NAILGUN['SATPASS'] = (
                conf.auth or ('admin', 'changeme'))
            self.NAILGUN['VERIFY'] = conf.verify or False
            self.NAILGUN['LABEL'] = label
        if not self.NAILGUN.get('CONFIG', None):
            server_conf = ServerConfig(url='')
            server_conf.url = self.NAILGUN.get('SATHOST', 'https://https://localhost')
            server_conf.auth = (
                self.NAILGUN.get('SATUSER', 'admin'),
                self.NAILGUN.get('SATPASS', 'changeme'))
            server_conf.verify = self.NAILGUN.get('VERIFY', False)
            server_conf.save(
                label=self.NAILGUN.get('LABEL', label))
            self.NAILGUN['CONFIG'] = server_conf
        return self.NAILGUN['CONFIG']

    def clear_nailgun(self):
        """Clear all current nailgun configurations"""
        ServerConfig(url='').save(
            label=self.NAILGUN['LABEL'], path=self.NAILGUN.get('path', None))
        for key in self.NAILGUN:
            self.NAILGUN[key] = None
        self.save_config()

    def clear_rizza(self):
        """Clear all current rizza configurations"""
        self.RIZZA = {}
        self.save_config()

    @staticmethod
    def yaml_print(in_dict=None):
        """Convert a dictionary to yaml string, and print it out"""
        print(yaml.dump(in_dict, default_flow_style=False))
