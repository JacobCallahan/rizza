"""Tests for the normalized PermutationStore telemetry backend."""

import json

import pytest

from rizza.helpers.telemetry import PermutationStore, _compute_hash


@pytest.fixture
def store(tmp_path):
    """Create a PermutationStore with a temporary database."""
    db_path = tmp_path / "test_telemetry" / "permutations.db"
    s = PermutationStore(db_path=db_path)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


class TestHashComputation:
    def test_deterministic(self):
        d1 = {"name": "gen_email", "org_id": "genetic_known"}
        d2 = {"org_id": "genetic_known", "name": "gen_email"}
        assert _compute_hash(d1) == _compute_hash(d2)

    def test_different_dicts_different_hashes(self):
        assert _compute_hash({"a": "x"}) != _compute_hash({"a": "y"})

    def test_single_param(self):
        h = _compute_hash({"name": "gen_alpha"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_canonical_json_used(self):
        canonical = json.dumps({"a": "x", "b": "y"}, separators=(",", ":"))
        import hashlib

        expected = hashlib.sha256(canonical.encode()).hexdigest()
        assert _compute_hash({"b": "y", "a": "x"}) == expected


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_tables_exist(self, store):
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        expected = {
            "methods",
            "parameters",
            "generators",
            "permutation_results",
            "permutation_vector_mapping",
        }
        assert expected <= names

    def test_index_exists(self, store):
        indexes = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()
        names = {r["name"] for r in indexes}
        assert "idx_vector_lookup" in names

    def test_idempotent_schema(self, store):
        store._ensure_schema()
        store._ensure_schema()

    def test_wal_mode(self, store):
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_on(self, store):
        fk = store._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


# ---------------------------------------------------------------------------
# Record and flush
# ---------------------------------------------------------------------------


class TestRecordAndFlush:
    def test_single_pass(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 1
        assert rows[0]["fail_count"] == 0

    def test_single_fail(self, store):
        store.record("Org.create", {"name": "gen_alpha"}, False)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 0
        assert rows[0]["fail_count"] == 1

    def test_multiple_records_batch(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, False)
        store.record("Org.update", {"name": "gen_uuid"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 3

    def test_buffer_cleared_after_flush(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        assert len(store._buffer) == 0

    def test_flush_empty_buffer(self, store):
        store.flush()


# ---------------------------------------------------------------------------
# Upsert behavior
# ---------------------------------------------------------------------------


class TestUpsertBehavior:
    def test_duplicate_increments_pass_count(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 2
        assert rows[0]["fail_count"] == 0

    def test_duplicate_increments_fail_count(self, store):
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 0
        assert rows[0]["fail_count"] == 2

    def test_mixed_pass_fail_accumulates(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 1
        assert rows[0]["fail_count"] == 1

    def test_different_vectors_separate_rows(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 2

    def test_same_vector_across_flushes(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_results").fetchall()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 1
        assert rows[0]["fail_count"] == 1


# ---------------------------------------------------------------------------
# Junction table (permutation_vector_mapping)
# ---------------------------------------------------------------------------


class TestJunctionTable:
    def test_mapping_created(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_vector_mapping").fetchall()
        assert len(rows) == 1

    def test_multi_param_mapping(self, store):
        store.record(
            "Org.create",
            {"name": "gen_email", "id": "gen_integer"},
            True,
        )
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_vector_mapping").fetchall()
        assert len(rows) == 2

    def test_status_defaults_to_included(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        row = store._conn.execute("SELECT status FROM permutation_vector_mapping").fetchone()
        assert row["status"] == "included"

    def test_mapping_not_duplicated_on_upsert(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        rows = store._conn.execute("SELECT * FROM permutation_vector_mapping").fetchall()
        assert len(rows) == 1

    def test_fk_integrity(self, store):
        store.record(
            "Org.create",
            {"name": "gen_email", "org_id": "gen_uuid"},
            True,
        )
        store.flush()
        mapping = store._conn.execute(
            "SELECT pvm.parameter_id, pvm.generator_id FROM permutation_vector_mapping pvm"
        ).fetchall()
        param_ids = {r["parameter_id"] for r in mapping}
        gen_ids = {r["generator_id"] for r in mapping}
        real_params = {
            r["id"] for r in store._conn.execute("SELECT id FROM parameters").fetchall()
        }
        real_gens = {r["id"] for r in store._conn.execute("SELECT id FROM generators").fetchall()}
        assert param_ids <= real_params
        assert gen_ids <= real_gens


# ---------------------------------------------------------------------------
# Topology population (methods, parameters, generators tables)
# ---------------------------------------------------------------------------


class TestTopologyPopulation:
    def test_method_created(self, store):
        store.record("Organization.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM methods").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "Organization.create"

    def test_parameter_created(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM parameters").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "name"

    def test_generator_created(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        rows = store._conn.execute("SELECT * FROM generators").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "gen_email"

    def test_multiple_generators(self, store):
        store.record(
            "Org.create",
            {"name": "gen_email", "id": "genetic_known"},
            True,
        )
        store.flush()
        rows = store._conn.execute("SELECT name FROM generators ORDER BY name").fetchall()
        names = [r["name"] for r in rows]
        assert "gen_email" in names
        assert "genetic_known" in names

    def test_method_cache_reused(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, True)
        store.flush()
        assert len(store._method_cache) == 1
        rows = store._conn.execute("SELECT * FROM methods").fetchall()
        assert len(rows) == 1

    def test_param_linked_to_method(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.update", {"name": "gen_alpha"}, True)
        store.flush()
        params = store._conn.execute(
            "SELECT p.name, m.name AS method_name "
            "FROM parameters p "
            "JOIN methods m ON m.id = p.method_id"
        ).fetchall()
        assert len(params) == 2
        method_names = {r["method_name"] for r in params}
        assert method_names == {"Org.create", "Org.update"}


# ---------------------------------------------------------------------------
# query_method_summary
# ---------------------------------------------------------------------------


class TestQueryMethodSummary:
    def test_basic_summary(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, False)
        store.record("Org.update", {"name": "gen_uuid"}, True)
        store.flush()

        rows = store.query_method_summary("Org")
        assert len(rows) == 2
        create = next(r for r in rows if r["name"] == "Org.create")
        assert create["total_permutations"] == 2
        assert create["total_passes"] == 1
        assert create["total_fails"] == 1

    def test_all_methods(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Host.list", {"id": "gen_integer"}, True)
        store.flush()

        rows = store.query_method_summary()
        names = {r["name"] for r in rows}
        assert names == {"Org.create", "Host.list"}

    def test_entity_filter(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Host.list", {"id": "gen_integer"}, True)
        store.flush()

        rows = store.query_method_summary("Org")
        assert len(rows) == 1
        assert rows[0]["name"] == "Org.create"

    def test_empty_db(self, store):
        assert store.query_method_summary() == []

    def test_accumulates_counts(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()

        rows = store.query_method_summary("Org")
        assert rows[0]["total_passes"] == 2
        assert rows[0]["total_fails"] == 1


# ---------------------------------------------------------------------------
# query_method_tree
# ---------------------------------------------------------------------------


class TestQueryMethodTree:
    def test_basic_tree(self, store):
        store.record(
            "Org.create",
            {"name": "gen_email", "id": "gen_integer"},
            True,
        )
        store.record(
            "Org.create",
            {"name": "gen_alpha", "id": "gen_integer"},
            False,
        )
        store.flush()

        rows = store.query_method_tree("Org.create")
        by_param = {}
        for r in rows:
            by_param.setdefault(r["param_name"], []).append(r)
        assert "name" in by_param
        assert "id" in by_param

        name_entries = {e["generator_name"]: e for e in by_param["name"]}
        assert name_entries["gen_email"]["pass_count"] == 1
        assert name_entries["gen_alpha"]["fail_count"] == 1

    def test_empty_method(self, store):
        assert store.query_method_tree("Org.nonexistent") == []

    def test_status_in_results(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()

        rows = store.query_method_tree("Org.create")
        assert len(rows) == 1
        assert rows[0]["status"] == "included"

    def test_multi_generator_per_param(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, False)
        store.record("Org.create", {"name": "gen_uuid"}, True)
        store.flush()

        rows = store.query_method_tree("Org.create")
        generators = {r["generator_name"] for r in rows}
        assert generators == {"gen_email", "gen_alpha", "gen_uuid"}

    def test_counts_aggregated_correctly(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()

        rows = store.query_method_tree("Org.create")
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 2
        assert rows[0]["fail_count"] == 1


# ---------------------------------------------------------------------------
# query_methods
# ---------------------------------------------------------------------------


class TestQueryMethods:
    def test_returns_sorted(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Host.list", {"id": "gen_integer"}, True)
        store.flush()
        assert store.query_methods() == ["Host.list", "Org.create"]

    def test_empty_db(self, store):
        assert store.query_methods() == []


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_empty_db(self, store):
        assert store.compute_coverage() == (0, 0)

    def test_single_method_single_param(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        tested, possible = store.compute_coverage()
        assert tested == 1
        assert possible == 1  # 1 generator ^ 1 param

    def test_multiple_generators_expand_space(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.create", {"name": "gen_alpha"}, False)
        store.flush()
        tested, possible = store.compute_coverage()
        assert tested == 2
        assert possible == 2  # 2 generators ^ 1 param

    def test_multi_param_cartesian_product(self, store):
        store.record("Org.create", {"name": "gen_email", "id": "gen_integer"}, True)
        store.record("Org.create", {"name": "gen_alpha", "id": "gen_integer"}, False)
        store.flush()
        tested, possible = store.compute_coverage()
        assert tested == 2
        # 3 generators (gen_email, gen_alpha, gen_integer) ^ 2 params = 9
        assert possible == 9

    def test_entity_filter(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Host.list", {"id": "gen_integer"}, True)
        store.flush()
        tested, possible = store.compute_coverage("Org")
        assert tested == 1
        # 2 total generators ^ 1 param for Org.create = 2
        assert possible == 2

    def test_multiple_methods_sum_possible(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.record("Org.update", {"id": "gen_integer"}, True)
        store.flush()
        tested, possible = store.compute_coverage()
        assert tested == 2
        # 2 generators total, each method has 1 param: 2^1 + 2^1 = 4
        assert possible == 4

    def test_generators_shared_across_methods(self, store):
        store.record("Org.create", {"name": "gen_email", "id": "gen_integer"}, True)
        store.record("Host.list", {"label": "gen_alpha"}, True)
        store.flush()
        tested, possible = store.compute_coverage()
        assert tested == 2
        # 3 generators total; Org.create has 2 params: 3^2=9, Host.list has 1 param: 3^1=3
        assert possible == 12


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------


class TestFromConfig:
    def test_derives_path(self, tmp_path):
        from unittest.mock import MagicMock

        config = MagicMock()
        config.telemetry_dir = tmp_path / "data" / "telemetry" / "sat" / "api"
        s = PermutationStore.from_config(config)
        assert s.db_path == config.telemetry_dir / "permutations.db"
        assert s.db_path.parent.exists()
        s.close()


# ---------------------------------------------------------------------------
# close flushes pending
# ---------------------------------------------------------------------------


class TestCloseFlushes:
    def test_close_flushes_pending(self, tmp_path):
        db_path = tmp_path / "close_test" / "permutations.db"
        s = PermutationStore(db_path=db_path)
        s.record("Org.create", {"name": "gen_email"}, True)
        s.close()

        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM permutation_results").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["pass_count"] == 1


# ---------------------------------------------------------------------------
# is_known_bad
# ---------------------------------------------------------------------------


class TestIsKnownBad:
    def test_unknown_permutation_not_bad(self, store):
        assert not store.is_known_bad("Org.create", {"name": "gen_email"})

    def test_failed_permutation_is_bad(self, store):
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        assert store.is_known_bad("Org.create", {"name": "gen_email"})

    def test_passed_permutation_not_bad(self, store):
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        assert not store.is_known_bad("Org.create", {"name": "gen_email"})

    def test_mixed_pass_fail_not_bad(self, store):
        store.record("Org.create", {"name": "gen_email"}, False)
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        assert not store.is_known_bad("Org.create", {"name": "gen_email"})

    def test_different_method_not_bad(self, store):
        store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        assert not store.is_known_bad("Org.update", {"name": "gen_email"})


# ---------------------------------------------------------------------------
# get_poison_pairs
# ---------------------------------------------------------------------------


class TestGetPoisonPairs:
    def test_no_data_returns_empty(self, store):
        assert store.get_poison_pairs("Org.create") == set()

    def test_below_min_attempts_not_poisoned(self, store):
        for _ in range(5):
            store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        assert store.get_poison_pairs("Org.create", min_attempts=10) == set()

    def test_above_min_attempts_poisoned(self, store):
        for _ in range(10):
            store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        pairs = store.get_poison_pairs("Org.create", min_attempts=10)
        assert ("name", "gen_email") in pairs

    def test_pair_with_pass_not_poisoned(self, store):
        for _ in range(10):
            store.record("Org.create", {"name": "gen_email"}, False)
        store.record("Org.create", {"name": "gen_email"}, True)
        store.flush()
        pairs = store.get_poison_pairs("Org.create", min_attempts=10)
        assert ("name", "gen_email") not in pairs

    def test_different_method_not_poisoned(self, store):
        for _ in range(10):
            store.record("Org.create", {"name": "gen_email"}, False)
        store.flush()
        assert store.get_poison_pairs("Org.update", min_attempts=10) == set()
