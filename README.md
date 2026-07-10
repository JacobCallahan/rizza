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
rizza [-h] {explore,validate,config,list}
```

### Explore

Uses a genetic algorithm to evolve toward a successful (or deliberately failing) API call for a given entity and method. Completed tests are saved to `~/rizza/data/genetic_tests/`.

By default, `explore` runs against **all entities** (`_all`) and targets only **methods that don't yet have a passing test** (`_new`). Async execution is on by default.

```bash
rizza explore --help

# Run against all entities, all untested methods (default)
rizza explore

# Explore a specific entity and method
rizza explore -e Organization -m create

# Explore all methods for one entity, including already-passing ones
rizza explore -e Organization -m _all

# Seek a failing result
rizza explore -e Organization -m create --seek-bad

# Skip dependency resolution
rizza explore -e Organization -m create --disable-dependencies

# Run synchronously
rizza explore --no-async

# Limit concurrency
rizza explore --async-limit 20

# Ignore saved results and start fresh
rizza explore -e Organization -m create --fresh
```

**Special `--method` values:**

| Value | Meaning |
|-------|---------|
| `_new` | Only methods without a saved passing test (default) |
| `_all` | Every method on the entity |
| `<name>` | A specific method by name |

**Special `--entity` values:**

| Value | Meaning |
|-------|---------|
| `_all` | Every known entity (default) |
| `<name>` | A specific entity by name |

### Validate

Re-runs saved tests from `~/rizza/data/genetic_tests/` to confirm they still pass. Generates a structured report capturing the test name, the actual values passed to the API, and the response. Async execution is on by default.

```bash
rizza validate --help

# Validate all saved tests (default)
rizza validate

# Validate a specific entity
rizza validate -e Organization

# Validate a specific entity and method
rizza validate -e Organization -m create

# Remove tests that fail validation
rizza validate --prune

# Run synchronously
rizza validate --no-async

# Write report to a custom path
rizza validate --report-path /tmp/my-report.yaml

# Write report as JSON
rizza validate --report-format json
```

**Reports** are auto-saved to `~/rizza/validation/` after every run. The filename reflects the scope of the validation:

| Scope | Filename |
|-------|---------|
| All entities | `satellite-01Jul26.yaml` |
| Specific entity | `satellite-Organization-01Jul26.yaml` |
| Entity + method | `satellite-Organization-create-01Jul26.yaml` |

Report structure:

```yaml
product: satellite
generated_at: "2026-07-01T12:00:00"
summary:
  total: 42
  passed: 38
  failed: 4
tests:
  - test_name: "Organization create positive"
    entity: Organization
    method: create
    mode: positive
    passed: true
    arg_dict:
      name: gen_alphanumeric
      organization_id: genetic_known
    resolved_args:
      name: "AbcDef123"
      organization_id: "42"
    response:
      id: 123
      name: AbcDef123
```

### Config

Inspect or modify the active configuration:

```bash
rizza config view
rizza config view genetics        # view a specific config chunk
rizza config set LOG_LEVEL debug  # set a value
rizza config init                 # write default config files
```

### List

Inspect what rizza knows about the loaded API plugin:

```bash
rizza list entities
rizza list methods -e Organization
rizza list methods -e Organization --new       # only untested methods
rizza list methods -e Organization --explored  # only methods with passing tests
rizza list fields -e Organization
rizza list args -e Organization -m create
rizza list input-methods
```

## Docker

```bash
docker build -t rizza .
# or
docker pull jacobcallahan/rizza

# Mount your local rizza directory to provide config and persist data
docker run --rm -v $(pwd):/root/rizza/:Z rizza explore -e Organization -m create

# Override connection at runtime — no config file edit needed
docker run --rm \
  -e rizza_connection_HOSTNAME=satellite.example.com \
  -e rizza_connection_PASSWORD=secret \
  -v $(pwd):/root/rizza/:Z \
  rizza explore -e Organization -m create
```

## Requirements

Python 3.10+
