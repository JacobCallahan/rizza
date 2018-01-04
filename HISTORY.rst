=======
History
=======

0.3.3(2018-01-04)
+++++++++++++++++

+ Added MAX RECURSIVE DEPTH to limit genetic_unknown recursion
+ Updated genetic_known and genetic_unknown methods
+ Added error checking to EntityTester pull methods
+ Expanded BASE_GENOME in test_genetics to lessen false failures

0.3.2(2018-01-03)
+++++++++++++++++

+ Added ability for rizza to recursively fill dependencies
+ Added new config and cli options for this change

0.3.1(2018-01-02)
+++++++++++++++++

* Fixed GeneticEntityTester._load_test

0.3.0(2017-12-31)
+++++++++++++++++

* Introducing Genetic Algorithm-based testing!
* Added genetic subcommand
* Added genetic_tester module
* Added initial tests for that module
* Minor tweaks and improvements

0.2.0(2017-11-28)
+++++++++++++++++

* Completely rewrote the config helper file
* Added tests for the new Config class
* Re-worked the cli and other pieces to take advantage
  of new config class changes.

0.1.7(2017-11-19)
+++++++++++++++++

* Added initial tests for genetic algoritm classes
* Radically optimized genetic algorithm implementation!

0.1.6(2017-10-06)
+++++++++++++++++

* Added find method to MaiMap
* Added helper file for configurations
* General Optimizations in entity_tester and __main__
* Added initial tests for entity_tester file

0.1.5(2017-10-04)
+++++++++++++++++

* Added Travis CI

0.1.4(2017-10-04)
+++++++++++++++++

* Added in basic tests
    - run ```rizza test``` to test
* Fixed some minor issues found while testing
* Changed some text helpers to return a bool

0.1.3(2017-10-03)
+++++++++++++++++

* Minor changes

0.1.2(2017-07-17)
+++++++++++++++++

* Added list subcommand

0.1.1(2017-03-06)
++++++++++++++++++

* Fixed logging

0.1.0(2017-03-03)
++++++++++++++++++

* Initital functionality added
    - brute force test generation, storage
    - nailgun configuration
    - Docker capability
* There be cowboys!
