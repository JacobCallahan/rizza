# rizza
An increasingly intelligent method to test RH Satellite.

Installation
------------
```pip install .```
or
```python setup.py install```

Usage
-----
```rizza [-h] {brute,config}```

Examples
--------
```rizza --help```

```rizza brute --help```

```rizza brute -e Product -o tester.txt --max-fields 2 --max-inputs 1 --method-exclude raw search read get payload```

```rizza brute -i 10tests.txt -l stdout```

```rizza config --help```

```rizza config nailgun -p demo```

```rizza config nailgun --show```

Docker
------
```docker build -t rizza .```
or
```docker pull jacobcallahan/rizza```

```docker run -it rizza brute --help```

```docker run -it -v $(pwd):/root/rizza/:Z rizza brute -e Product -o docker.txt --max-fields 2 --max-inputs 1 --method-exclude raw search read get payload```

Note
----
This project only explicitly supports python 3.
