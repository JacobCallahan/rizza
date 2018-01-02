#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'attrs',
    'nailgun',
    'pyyaml',
    'pytest'
]

setup(
    name='rizza',
    version='0.3.1',
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
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ]
)
