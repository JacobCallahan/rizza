# rizza
An increasingly intelligent method to test RH Satellite.

Installation
------------
```pip install .```
or
```python setup.py install```

After installation copy/rename the example rizza.yaml configuration, located in config/ to rizza.yaml

Usage
-----
```rizza [-h] {brute,genetic,config,list,test}```

Brute Force Testing
-------------------
Rizza's most basic, and time consuming, operation is a brute force method of testing entities. It will try every combination of an entity's methods, fields, arguments, and available input methods.
It is highly recommended that you limit the scope of this kind of test with --max-field, --max-inputs, and the exclude options available. An unlimited test can easily generate trillions of combinations and will likely take longer than the lifecycle of your product.

**Examples:**
```rizza brute --help```

```rizza brute -e Product -o tester.txt --max-fields 2 --max-inputs 1 --method-exclude raw search read get payload```

```rizza brute -i 10tests.txt -l stdout```

Genetic Algorithm-Based Testing
-------------------------------
Rizza is able to test entities (via their methods) using genetic algorithms to evolve toward a positive or negative goal. You can adjust the scoring criteria in config/rizza.yaml.
Rizza, by default, will recursively try to create entities it both does and doesn't know how to, in order to resolve dependencies. You can limit or turn this off both in the config or at run-time with cli args. Note that this recursive process adds a significant amount of time.
Once a test completes, it is saved in data/genetic_tests/

**Examples:**
```rizza genetic --help```

```rizza genetic -e Organization -m create```

```rizza genetic -e Organization -m create --max-generations 100 --seek-bad --fresh --disable-recursion```

Configuration
-------------
Rizza's main configuration file is located in config/rizza.yaml. After cloning, you will need to copy the example file to rizza.yaml. Most of these configurations have CLI overrides, and there are even some limited support for environment variables (SATHOST, SATUSER, SATPASS, CONFILE).
Additionally, there is support for modifying some configuration options through rizza's cli.

**Examples:**
```rizza config --help```

```rizza config nailgun -p demo```

```rizza config nailgun --show```

List
----
Rizza can tell you all the information it knows about your product plugin using the list command. These results are currently unfiltered, so will show anything that meets rizza's criteria for what constitutes an entity.

**Examples:**
```rizza list entities```

```rizza list methods -e Organization```

Test
----
Rizza is also able to test itself, using pytest. This is mainly useful for testing your container images, to verify everything is working before you begin using rizza.
You can even pass in pytest args by adding the --args flag.
**Examples:**
```rizza test```

```rizza test --args=-v```

Docker
------
Rizza is also available with automatic builds on dockerhub.
You can either pull down the latest, or a specific released version.
Additionally, you can build your own image locally. You will want to mount the local rizza directory to provide your configuration and keep any data rizza creates.

**Examples:**
```docker build -t rizza .```
or
```docker pull jacobcallahan/rizza```

```docker run -it rizza brute --help```

```docker run -it -v $(pwd):/root/rizza/:Z rizza brute -e Product -o docker.txt --max-fields 2 --max-inputs 1 --method-exclude raw search read get payload```

```docker run --rm -v $(pwd):/root/rizza/:Z jacobcallahan/rizza genetic -e Organization```

Note
----
This project only explicitly supports python 3.4+, and will likely be 3.6+ in the near future.
