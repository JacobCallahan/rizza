# rizza
An increasingly intelligent method to test RH Satellite.

## Installation

```
pip install .
```

Rizza creates a `~/rizza/` directory on first run, including a `config/` subdirectory for your configuration files.

## Configuration

Rizza uses [picoconf](https://github.com/JacobCallahan/picoconf) `.pconf` files. Copy the example files from `config/` to `~/rizza/config/` and fill in your values:

```
~/rizza/config/
    rizza.pconf       # top-level settings, imports the files below
    genetics.pconf    # genetic algorithm tuning
    connection.pconf  # target host credentials
```

**`connection.pconf`**
```yaml
_envar_prefix: rizza_connection
HOSTNAME: satellite.example.com
USERNAME: admin
PASSWORD: changeme
```

**`genetics.pconf`**
```yaml
_envar_prefix: rizza_genetics
POPULATION_COUNT: 100
MAX_GENERATIONS: 10000
# ... see config/genetics.pconf.example for all options
```

**`rizza.pconf`**
```yaml
_envar_prefix: rizza
_import:
  - genetics.pconf
  - connection.pconf
APIX_LIB_PATH: ~/rizza/apix_generated.py
LOG_LEVEL: info
LOG_PATH: logs/rizza.log
```

### Runtime overrides via environment variables

Each config file owns a prefix. Individual keys can be overridden at runtime without touching any file:

```bash
# Override connection settings
export rizza_connection_HOSTNAME=prod-satellite.example.com
export rizza_connection_PASSWORD=secret

# Override genetics settings
export rizza_genetics_MAX_GENERATIONS=500
export rizza_genetics_POPULATION_COUNT=50

# Override top-level settings
export rizza_LOG_LEVEL=debug
```

## Usage

```
rizza [-h] {genetic,config,list,test}
```

### Genetic Algorithm Testing

Rizza uses genetic algorithms to evolve toward a successful (or deliberately failing) API call for a given entity and method. By default it will recursively resolve entity dependencies. Completed tests are saved to `~/rizza/data/genetic_tests/`.

```bash
rizza genetic --help

# Basic usage
rizza genetic -e Organization -m create

# Seek a bad result, skip dependency resolution, run async
rizza genetic -e Organization -m create --seek-bad --run-async

# Run against all known entities
rizza genetic -e All --run-async --async-limit 20

# Prune stale passing tests
rizza genetic -e Organization --prune
```

### Config

Inspect the active configuration:

```bash
rizza config view
```

### List

Inspect what rizza knows about the loaded API plugin:

```bash
rizza list entities
rizza list methods -e Organization
rizza list fields -e Organization
rizza list args -e Organization -m create
```

### Test

Run rizza's own test suite (useful for verifying a container image or dev environment):

```bash
rizza test
rizza test --args=-v
rizza test --args=tests/test_genetic_tester.py
```

## Docker

```bash
docker build -t rizza .
# or
docker pull jacobcallahan/rizza

# Mount your local rizza directory to provide config and persist data
docker run --rm -v $(pwd):/root/rizza/:Z rizza genetic -e Organization -m create

# Override connection at runtime — no config file edit needed
docker run --rm \
  -e rizza_connection_HOSTNAME=satellite.example.com \
  -e rizza_connection_PASSWORD=secret \
  -v $(pwd):/root/rizza/:Z \
  rizza genetic -e Organization -m create
```

## Requirements

Python 3.10+
