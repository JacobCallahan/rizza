"""SQLite-backed telemetry store for GA permutation results.

Normalized schema with a junction table linking each parameter-generator
pair in a permutation vector to first-class FK-backed rows.  Pass/fail
counts accumulate via upsert; scores are not stored — variance and range
are derived mathematically from execution counts at query time.
"""

import hashlib
import json
import logging
from pathlib import Path
import sqlite3

import attr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS methods (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS parameters (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    method_id INTEGER NOT NULL,
    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE,
    UNIQUE(name, method_id)
);

CREATE TABLE IF NOT EXISTS generators (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS permutation_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    method_id        INTEGER NOT NULL,
    permutation_hash TEXT    NOT NULL,
    pass_count       INTEGER NOT NULL DEFAULT 0,
    fail_count       INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE,
    UNIQUE(method_id, permutation_hash)
);

CREATE TABLE IF NOT EXISTS permutation_vector_mapping (
    permutation_result_id INTEGER NOT NULL,
    parameter_id          INTEGER NOT NULL,
    generator_id          INTEGER NOT NULL,
    status                TEXT    NOT NULL DEFAULT 'included',
    PRIMARY KEY (permutation_result_id, parameter_id),
    FOREIGN KEY (permutation_result_id)
        REFERENCES permutation_results(id) ON DELETE CASCADE,
    FOREIGN KEY (parameter_id)
        REFERENCES parameters(id) ON DELETE CASCADE,
    FOREIGN KEY (generator_id)
        REFERENCES generators(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vector_lookup
ON permutation_vector_mapping(parameter_id, generator_id, status);
"""

# ---------------------------------------------------------------------------
# Upsert DML
# ---------------------------------------------------------------------------

_UPSERT_RESULT = """\
INSERT INTO permutation_results
    (method_id, permutation_hash, pass_count, fail_count)
VALUES (?, ?, ?, ?)
ON CONFLICT(method_id, permutation_hash) DO UPDATE SET
    pass_count = pass_count + excluded.pass_count,
    fail_count = fail_count + excluded.fail_count
"""

_INSERT_MAPPING = """\
INSERT OR IGNORE INTO permutation_vector_mapping
    (permutation_result_id, parameter_id, generator_id, status)
VALUES (?, ?, ?, 'included')
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_hash(arg_dict):
    """Return a deterministic SHA-256 hex digest for *arg_dict*."""
    canonical = json.dumps(dict(sorted(arg_dict.items())), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


@attr.s()
class PermutationStore:
    """Accumulates GA permutation results and flushes to a normalized SQLite schema."""

    db_path = attr.ib(validator=attr.validators.instance_of(Path))
    _conn = attr.ib(init=False, default=None, repr=False)
    _buffer = attr.ib(init=False, factory=list, repr=False)
    _method_cache = attr.ib(init=False, factory=dict, repr=False)
    _param_cache = attr.ib(init=False, factory=dict, repr=False)
    _gen_cache = attr.ib(init=False, factory=dict, repr=False)

    # -- lifecycle -----------------------------------------------------------

    def __attrs_post_init__(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self):
        self._conn.executescript(_SCHEMA)

    @classmethod
    def from_config(cls, config):
        """Construct a store rooted at *config.telemetry_dir*."""
        db_path = config.telemetry_dir / "permutations.db"
        return cls(db_path=db_path)

    def close(self):
        """Flush remaining buffer and close the database connection."""
        if self._conn:
            self.flush()
            self._conn.close()
            self._conn = None

    # -- ID resolution (cached) ---------------------------------------------

    def _resolve_method_id(self, name):
        cached = self._method_cache.get(name)
        if cached is not None:
            return cached
        self._conn.execute("INSERT OR IGNORE INTO methods (name) VALUES (?)", (name,))
        row = self._conn.execute("SELECT id FROM methods WHERE name = ?", (name,)).fetchone()
        self._method_cache[name] = row["id"]
        return row["id"]

    def _resolve_parameter_id(self, name, method_id):
        key = (name, method_id)
        cached = self._param_cache.get(key)
        if cached is not None:
            return cached
        self._conn.execute(
            "INSERT OR IGNORE INTO parameters (name, method_id) VALUES (?, ?)",
            (name, method_id),
        )
        row = self._conn.execute(
            "SELECT id FROM parameters WHERE name = ? AND method_id = ?",
            (name, method_id),
        ).fetchone()
        self._param_cache[key] = row["id"]
        return row["id"]

    def _resolve_generator_id(self, name):
        cached = self._gen_cache.get(name)
        if cached is not None:
            return cached
        self._conn.execute("INSERT OR IGNORE INTO generators (name) VALUES (?)", (name,))
        row = self._conn.execute("SELECT id FROM generators WHERE name = ?", (name,)).fetchone()
        self._gen_cache[name] = row["id"]
        return row["id"]

    # -- write path ----------------------------------------------------------

    def record(self, method_name, arg_dict, passed):
        """Buffer a permutation result for later batch write.

        :param method_name: Fully qualified method (e.g. ``"Organization.create"``).
        :param arg_dict: ``{param_name: generator_name}`` mapping.
        :param passed: Boolean — True for pass, False for fail.
        """
        self._buffer.append((method_name, dict(arg_dict), bool(passed)))

    def flush(self):
        """Batch-write all buffered records in a single transaction."""
        if not self._buffer:
            return
        with self._conn:
            for method_name, arg_dict, passed in self._buffer:
                method_id = self._resolve_method_id(method_name)
                perm_hash = _compute_hash(arg_dict)
                pass_count = 1 if passed else 0
                fail_count = 0 if passed else 1

                self._conn.execute(
                    _UPSERT_RESULT,
                    (method_id, perm_hash, pass_count, fail_count),
                )

                result_row = self._conn.execute(
                    "SELECT id FROM permutation_results "
                    "WHERE method_id = ? AND permutation_hash = ?",
                    (method_id, perm_hash),
                ).fetchone()
                result_id = result_row["id"]

                for param_name, gen_name in arg_dict.items():
                    param_id = self._resolve_parameter_id(param_name, method_id)
                    gen_id = self._resolve_generator_id(gen_name)
                    self._conn.execute(_INSERT_MAPPING, (result_id, param_id, gen_id))
        self._buffer.clear()

    # -- read path -----------------------------------------------------------

    def query_methods(self):
        """Return a sorted list of method names that have permutation data."""
        rows = self._conn.execute(
            "SELECT DISTINCT m.name "
            "FROM methods m "
            "JOIN permutation_results pr ON pr.method_id = m.id "
            "ORDER BY m.name"
        ).fetchall()
        return [r["name"] for r in rows]

    def query_method_summary(self, method_filter=None):
        """Per-method summary with pass/fail totals.

        :param method_filter: When provided, only return methods whose name
            starts with ``"{method_filter}."``.  Pass an entity name to scope
            the summary to a single entity.
        :returns: List of dicts with keys ``name``, ``total_permutations``,
            ``total_passes``, ``total_fails``.
        """
        sql = """\
            SELECT
                m.name,
                COUNT(pr.id) AS total_permutations,
                SUM(pr.pass_count) AS total_passes,
                SUM(pr.fail_count) AS total_fails
            FROM methods m
            LEFT JOIN permutation_results pr ON m.id = pr.method_id
            {where}
            GROUP BY m.id
            ORDER BY m.name
        """
        if method_filter:
            rows = self._conn.execute(
                sql.format(where="WHERE m.name LIKE ?"),
                (f"{method_filter}.%",),
            ).fetchall()
        else:
            rows = self._conn.execute(sql.format(where="")).fetchall()
        return [dict(r) for r in rows]

    def compute_coverage(self, method_filter=None):
        """Return ``(tested, possible)`` permutation counts.

        *tested* is the number of unique permutation vectors recorded.
        *possible* is the Cartesian product of all known generators across
        each method's parameter slots, summed across methods.
        """
        total_generators = self._conn.execute("SELECT COUNT(*) FROM generators").fetchone()[0]
        if total_generators == 0:
            return 0, 0

        where = "WHERE m.name LIKE ?" if method_filter else ""
        params = (f"{method_filter}.%",) if method_filter else ()

        tested = self._conn.execute(
            f"SELECT COUNT(*) FROM permutation_results pr "
            f"JOIN methods m ON m.id = pr.method_id {where}",
            params,
        ).fetchone()[0]

        method_params = self._conn.execute(
            f"SELECT m.id, COUNT(p.id) AS param_count "
            f"FROM methods m "
            f"JOIN parameters p ON p.method_id = m.id "
            f"{where} GROUP BY m.id",
            params,
        ).fetchall()

        possible = sum(total_generators ** row["param_count"] for row in method_params)
        return tested, possible

    def is_known_bad(self, method_name, arg_dict):
        """Return True if this exact permutation has been tried and never passed."""
        perm_hash = _compute_hash(arg_dict)
        row = self._conn.execute(
            "SELECT 1 FROM permutation_results pr "
            "JOIN methods m ON m.id = pr.method_id "
            "WHERE m.name = ? AND pr.permutation_hash = ? "
            "AND pr.pass_count = 0 AND pr.fail_count > 0",
            (method_name, perm_hash),
        ).fetchone()
        return row is not None

    def get_poison_pairs(self, method_name, min_attempts=10):
        """Return (param, generator) pairs that have never appeared in a passing permutation.

        Only pairs with at least *min_attempts* total occurrences are considered —
        a pair seen once and failed is noise, not signal.

        :returns: set of ``(param_name, generator_name)`` tuples.
        """
        rows = self._conn.execute(
            """\
            SELECT p.name AS param_name, g.name AS generator_name,
                   SUM(pr.pass_count) AS total_passes,
                   SUM(pr.fail_count) AS total_fails
            FROM permutation_vector_mapping pvm
            JOIN permutation_results pr ON pr.id = pvm.permutation_result_id
            JOIN parameters p          ON p.id  = pvm.parameter_id
            JOIN generators g          ON g.id  = pvm.generator_id
            JOIN methods m             ON m.id  = pr.method_id
            WHERE m.name = ?
            GROUP BY p.name, g.name
            HAVING SUM(pr.pass_count) = 0
               AND (SUM(pr.pass_count) + SUM(pr.fail_count)) >= ?
            """,
            (method_name, min_attempts),
        ).fetchall()
        return {(r["param_name"], r["generator_name"]) for r in rows}

    def query_method_tree(self, method_name):
        """Per-parameter, per-status, per-generator pass/fail breakdown.

        :param method_name: Fully qualified method name.
        :returns: List of dicts with keys ``param_name``, ``status``,
            ``generator_name``, ``pass_count``, ``fail_count``.
        """
        rows = self._conn.execute(
            """\
            SELECT
                p.name  AS param_name,
                pvm.status,
                g.name  AS generator_name,
                SUM(pr.pass_count) AS pass_count,
                SUM(pr.fail_count) AS fail_count
            FROM permutation_vector_mapping pvm
            JOIN permutation_results pr ON pr.id = pvm.permutation_result_id
            JOIN parameters p          ON p.id  = pvm.parameter_id
            JOIN generators g          ON g.id  = pvm.generator_id
            JOIN methods m             ON m.id  = pr.method_id
            WHERE m.name = ?
            GROUP BY p.name, pvm.status, g.name
            ORDER BY p.name, pvm.status,
                     (SUM(pr.pass_count) + SUM(pr.fail_count)) DESC
            """,
            (method_name,),
        ).fetchall()
        return [dict(r) for r in rows]
