#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path
from setuptools import setup
from setuptools.command.install import install
from shutil import copy

class PostInstallCommand(install):
    def run(self):
        home = Path.home()
        # copy example config file
        config_file = Path('config/rizza.yaml.example')
        dest_file = home.joinpath('rizza/config/rizza.yaml.example')
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            copy(config_file.absolute(), dest_file)
        except:
            # the files are the same
            pass
        install.run(self)

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'attrs',
    'logzero',
    'nailgun',
    'pyyaml',
    'pytest'
]

setup(
    cmdclass={'install': PostInstallCommand},
    name='rizza',
    version='0.5.1',
    description="An increasingly intelligent method to test RH Satellite.",
    long_description=readme + '\n\n' + history,
    author="Jacob J Callahan",
    author_email='jacob.callahan05@@gmail.com',
    url='https://github.com/JacobCallahan/rizza',
    packages=['rizza', 'rizza.helpers'],
    # package_dir={'rizza': 'rizza'},
    entry_points={
        'console_scripts': [
            'rizza=rizza.__main__:Main'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="GNU General Public License v3",
    zip_safe=False,
    keywords='rizza',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ]
)
