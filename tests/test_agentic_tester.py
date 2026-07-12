"""Tests for rizza.agentic_tester."""
from pathlib import Path
import tempfile
from unittest.mock import MagicMock

import pytest

from rizza import genetic_tester
from rizza.agentic_tester import (
    _TORCH_AVAILABLE,
    ADD_PARAM,
    DROP_PARAM,
    NOOP,
    TARGETED_SWAP,
    AgenticPayloadLearner,
    APIResultAdapter,
    CategoricalStateEncoder,
    CLIResultAdapter,
    InteractionResult,
    QTablePolicy,
    apply_action,
)
from rizza.helpers import config
from rizza.helpers.misc import extract_validation_errors

_EXAMPLE_DIR = Path(__file__).parent.parent / "config"


@pytest.fixture(scope="module")
def conf():
    with tempfile.TemporaryDirectory() as tmpdir:
        for ex in _EXAMPLE_DIR.glob("*.pconf.example"):
            (Path(tmpdir) / ex.name.removesuffix(".example")).write_text(ex.read_text())
        yield config.Config(cfg_dir=tmpdir)


def _make_config(**kwargs):
    """Build a minimal agentic config namespace."""
    cfg = MagicMock()
    cfg.enabled = True
    cfg.max_candidates_per_generation = kwargs.get("max_candidates", 5)
    cfg.max_steps_per_candidate = kwargs.get("max_steps", 5)
    cfg.use_embeddings = False
    cfg.bucket_similarity_threshold = 0.85
    policy = MagicMock()
    policy.alpha = 0.1
    policy.gamma = 0.95
    policy.epsilon = 1.0  # always explore in tests
    policy.epsilon_decay = 1.0
    cfg.policy = policy
    reward = MagicMock()
    reward.success = 20
    reward.improved = 5
    reward.new_error = 3
    reward.same = -1
    reward.regressed = -2
    reward.server_error = -5
    reward.targeted_success = 8
    cfg.reward = reward
    cfg.validation_override_prob = kwargs.get("validation_override_prob", 0.5)
    cfg.validation_override_decay = kwargs.get("validation_override_decay", 0.995)
    cfg.recommender_batch_size = kwargs.get("recommender_batch_size", 8)
    cfg.recommender_epsilon_decay_per_episode = kwargs.get(
        "recommender_epsilon_decay_per_episode", 0.998
    )
    return cfg


def _make_learner(results_queue=None, judge_map=None, **kwargs):
    """Build an AgenticPayloadLearner with a mock execute pipeline."""
    results_queue = results_queue or []
    judge_map = judge_map or {}
    call_counter = {"n": 0}

    def genes_to_task_fn(genes):
        task = MagicMock()

        def execute():
            idx = call_counter["n"]
            call_counter["n"] += 1
            return (
                results_queue[idx]
                if idx < len(results_queue)
                else {"fail": {"unhandled": "no more results"}}
            )

        task.execute = execute
        return task

    def judge_fn(result):
        for key, pts in (judge_map or {}).items():
            if key in str(result):
                return pts
        return -100

    cfg = _make_config(**kwargs)
    return AgenticPayloadLearner(
        config=cfg,
        judge_fn=judge_fn,
        genes_to_task_fn=genes_to_task_fn,
        type_pools={"name": ["gen_alphanumeric", "gen_utf8"], "label": ["gen_alphanumeric"]},
        available_params=["name", "label", "description"],
        seek_bad=False,
    )


def _make_organism(genes, points=0):
    from rizza.helpers.genetics import Organism

    org = Organism(genes=genes)
    org.points = points
    return org


# ── InteractionResult + APIResultAdapter ──────────────────────────────────────

adapter = APIResultAdapter()


def test_adapt_pass_result():
    result = {"pass": {"id": 1}}
    ir = adapter.adapt(result)
    assert ir.success is True
    assert ir.status_category == "success"
    assert ir.error_class == ""


def test_adapt_http_error():
    result = {"fail": {"HTTPError": {"response": {"status": 422}}}}
    ir = adapter.adapt(result)
    assert ir.success is False
    assert ir.error_class == "HTTPError"
    assert ir.status_category == "client_error"


def test_adapt_http_server_error():
    result = {"fail": {"HTTPError": {"response": {"code": "500"}}}}
    ir = adapter.adapt(result)
    assert ir.status_category == "server_error"


def test_adapt_type_error():
    result = {"fail": {"TypeError": ("unexpected type",)}}
    ir = adapter.adapt(result)
    assert ir.error_class == "TypeError"
    assert ir.status_category == "client_error"


def test_adapt_unhandled():
    result = {"fail": {"unhandled": "something broke"}}
    ir = adapter.adapt(result)
    assert ir.error_class == "unhandled"
    assert ir.status_category == "unknown"


def test_flatten_to_text_nested():
    from rizza.interface_adapter import _flatten_to_text

    data = {"HTTPError": {"response": {"message": "bad value", "field": "name"}}}
    text = _flatten_to_text(data)
    assert "bad value" in text
    assert "name" in text
    assert len(text) > 0


# ── CategoricalStateEncoder ───────────────────────────────────────────────────

encoder = CategoricalStateEncoder()


def _make_ir(
    status="client_error", error_class="HTTPError", text="some error", validation_errors=None
):
    return InteractionResult(
        success=False,
        output_text=text,
        status_category=status,
        error_class=error_class,
        raw={},
        validation_errors=validation_errors or {},
    )


def test_encode_produces_hashable():
    ir = _make_ir()
    genes = [["name"], ["gen_alphanumeric"]]
    key = encoder.encode(ir, genes, 0, 0, 0)
    assert isinstance(key, tuple)
    # Verify it can be used as a dict key
    d = {key: 1}
    assert d[key] == 1


def test_same_error_same_state():
    ir = _make_ir()
    genes = [["name"], ["gen_alphanumeric"]]
    k1 = encoder.encode(ir, genes, 0, 0, 0)
    k2 = encoder.encode(ir, genes, 0, 0, 0)
    assert k1 == k2


def test_different_errors_usually_different():
    ir1 = _make_ir(error_class="HTTPError", text="422 error")
    ir2 = _make_ir(error_class="TypeError", text="wrong type")
    genes = [["name"], ["gen_alphanumeric"]]
    k1 = encoder.encode(ir1, genes, 0, 0, 0)
    k2 = encoder.encode(ir2, genes, 0, 0, 0)
    assert k1 != k2


def test_state_finite_for_varying_text():
    genes = [["name"], ["gen_alphanumeric"]]
    states = set()
    for i in range(100):
        ir = _make_ir(text=f"unique error message number {i}")
        states.add(encoder.encode(ir, genes, 0, 0, 0))
    assert len(states) <= 16


# ── apply_action ──────────────────────────────────────────────────────────────

TYPE_POOLS = {
    "name": ["gen_alphanumeric", "gen_utf8", "gen_uuid"],
    "label": ["gen_alphanumeric", "gen_utf8"],
}
AVAILABLE = ["name", "label", "description"]


def test_add_preserves_pairing():
    genes = [["name"], ["gen_alphanumeric"]]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE)
    assert len(result[0]) == len(result[1])


def test_add_picks_unused_param():
    genes = [["name"], ["gen_alphanumeric"]]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE)
    if len(result[0]) > 1:  # might be skipped if all params present
        assert result[0][-1] not in ["name"]


def test_drop_preserves_pairing():
    genes = [["name", "label"], ["gen_alphanumeric", "gen_utf8"]]
    result = apply_action(genes, DROP_PARAM, TYPE_POOLS, AVAILABLE)
    assert len(result[0]) == len(result[1])


def test_drop_floor_at_one():
    genes = [["name"], ["gen_alphanumeric"]]
    result = apply_action(genes, DROP_PARAM, TYPE_POOLS, AVAILABLE)
    assert len(result[0]) == 1
    assert len(result[1]) == 1


def test_drop_protects_required_params():
    genes = [["name", "label"], ["gen_alphanumeric", "gen_utf8"]]
    for _ in range(50):
        result = apply_action(genes, DROP_PARAM, TYPE_POOLS, AVAILABLE, required_params={"name"})
        assert "name" in result[0]


def test_drop_noop_when_all_required():
    genes = [["name", "label"], ["gen_alphanumeric", "gen_utf8"]]
    result = apply_action(
        genes, DROP_PARAM, TYPE_POOLS, AVAILABLE, required_params={"name", "label"}
    )
    assert len(result[0]) == 2


def test_noop_unchanged():
    genes = [["name", "label"], ["gen_alphanumeric", "gen_utf8"]]
    result = apply_action(genes, NOOP, TYPE_POOLS, AVAILABLE)
    assert result[0] == genes[0]
    assert result[1] == genes[1]


def test_apply_action_does_not_mutate_input():
    genes = [["name"], ["gen_alphanumeric"]]
    original_0 = genes[0][:]
    original_1 = genes[1][:]
    apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE)
    assert genes[0] == original_0
    assert genes[1] == original_1


# ── QTablePolicy ──────────────────────────────────────────────────────────────


def test_initial_action_is_exploratory():
    policy = QTablePolicy(epsilon=1.0)
    counts = [0] * 4
    for _ in range(200):
        counts[policy.select_action(("some", "key"))] += 1
    # All actions should be represented with high epsilon
    assert all(c > 0 for c in counts)


def test_update_changes_q_values():
    policy = QTablePolicy(epsilon=0.0, alpha=1.0, gamma=0.0)
    state = ("client_error", "HTTPError", "bad", 1, 0, 0, False)
    policy.update(state, ADD_PARAM, 5.0, state)
    assert policy.q_table[state][ADD_PARAM] == 5.0


def test_exploitation_after_learning():
    policy = QTablePolicy(epsilon=0.0, alpha=1.0, gamma=0.0)
    state = ("client_error", "HTTPError", "bad", 1, 0, 0, False)
    policy.update(state, ADD_PARAM, 10.0, state)
    policy.update(state, DROP_PARAM, 2.0, state)
    action = policy.select_action(state)
    assert action == ADD_PARAM


# ── Bucketing + Elite Selection ───────────────────────────────────────────────


def test_bucket_groups_same_errors():
    learner = _make_learner()
    err = {"fail": {"HTTPError": {"detail": "missing field"}}}
    org1 = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    org2 = _make_organism([["label"], ["gen_utf8"]], points=-200)
    buckets = learner._bucket_organisms([(org1, err), (org2, err)])
    assert len(buckets) == 1
    assert len(next(iter(buckets.values()))) == 2


def test_bucket_skips_successes():
    learner = _make_learner()
    org = _make_organism([["name"], ["gen_alphanumeric"]])
    buckets = learner._bucket_organisms([(org, {"pass": {"id": 1}})])
    assert len(buckets) == 0


def test_bucket_skips_server_errors():
    learner = _make_learner()
    org = _make_organism([["name"], ["gen_alphanumeric"]])
    err = {"fail": {"HTTPError": {"response": {"code": "500"}}}}
    buckets = learner._bucket_organisms([(org, err)])
    assert len(buckets) == 0


def test_elite_selects_fittest():
    learner = _make_learner()
    err = {"fail": {"TypeError": ("bad type",)}}
    org_low = _make_organism([["name"], ["gen_alphanumeric"]], points=-500)
    org_high = _make_organism([["name"], ["gen_utf8"]], points=-100)
    buckets = learner._bucket_organisms([(org_low, err), (org_high, err)])
    elites = learner._select_elites(buckets)
    assert len(elites) == 1
    assert elites[0][0].points == -100


def test_elite_cap():
    learner = _make_learner(max_candidates=2)
    errors = [{"fail": {"TypeError": (f"error {i}",)}} for i in range(5)]
    orgs = [_make_organism([["name"], ["gen_alphanumeric"]], points=-i * 10) for i in range(5)]
    buckets = learner._bucket_organisms(list(zip(orgs, errors, strict=False)))
    elites = learner._select_elites(buckets)
    assert len(elites) == 2


# ── Episode Loop ──────────────────────────────────────────────────────────────


def test_episode_finds_success():
    results = [
        {"fail": {"TypeError": ("bad",)}},
        {"pass": {"id": 42}},
    ]
    judge_map = {"pass": 500, "fail": -200}
    learner = _make_learner(results_queue=results, judge_map=judge_map, max_steps=5)
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    initial_result = {"fail": {"TypeError": ("bad",)}}
    outcome = learner._run_episode(org, initial_result, {})
    assert outcome is not None
    _, new_points, new_result = outcome
    assert "pass" in new_result or new_points > -200


def test_episode_unwinds_on_server_error():
    results = [
        {"fail": {"HTTPError": {"response": {"code": "500"}}}},
        {"fail": {"TypeError": ("bad",)}},
    ]
    judge_map = {"pass": 500, "fail": -100}
    learner = _make_learner(results_queue=results, judge_map=judge_map, max_steps=3)
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-100)
    initial_result = {"fail": {"TypeError": ("bad",)}}
    # Should not raise; episode should handle server error gracefully
    learner._run_episode(org, initial_result, {})
    # outcome may be None (no improvement) or a tuple — just verify no crash


def test_episode_returns_none_when_no_improvement():
    results = [{"fail": {"TypeError": ("same error",)}} for _ in range(10)]
    judge_map = {"TypeError": -200}
    learner = _make_learner(results_queue=results, judge_map=judge_map, max_steps=5)
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    initial_result = {"fail": {"TypeError": ("same error",)}}
    outcome = learner._run_episode(org, initial_result, {})
    assert outcome is None


def test_episode_respects_max_steps():
    results = [{"fail": {"TypeError": (f"err {i}",)}} for i in range(100)]
    learner = _make_learner(results_queue=results, judge_map={}, max_steps=3)
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    initial_result = {"fail": {"TypeError": ("err initial",)}}
    # Should terminate after max_steps without error
    learner._run_episode(org, initial_result, {})


# ── Integration ───────────────────────────────────────────────────────────────


def test_disabled_agentic_no_effect(conf):
    """With agentic.enabled=false (default), _agentic_learner should be None."""
    gen_test = genetic_tester.GeneticEntityTester(conf, "Organization", "create")
    assert gen_test._agentic_learner is None


def test_learn_from_generation_returns_improvements():
    results_queue = [{"pass": {"id": 1}}]
    judge_map = {"pass": 500}
    learner = _make_learner(results_queue=results_queue, judge_map=judge_map, max_steps=3)
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    err_result = {"fail": {"TypeError": ("bad type",)}}
    improvements = learner.learn_from_generation([(org, err_result)], {})
    # Should find the pass result and report improvement
    assert len(improvements) == 1
    _, _, new_points, new_result = improvements[0]
    assert "pass" in new_result


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_embedding_encoder_produces_tensor():
    from rizza.agentic_tester import EmbeddingStateEncoder

    encoder = EmbeddingStateEncoder()
    ir = InteractionResult(
        success=False,
        output_text="Name can't be blank",
        status_category="client_error",
        error_class="HTTPError",
        raw={},
    )
    genes = [["name"], ["gen_alphanumeric"]]
    state = encoder.encode(ir, genes, 0, 0, 0)
    import torch

    assert isinstance(state, torch.Tensor)
    assert state.shape[0] == 388


# ── Persistence ───────────────────────────────────────────────────────────────


def test_save_and_load_qtable():
    with tempfile.TemporaryDirectory() as tmpdir:
        learner = _make_learner(max_steps=3)
        learner.base_dir = tmpdir  # product="default", interface="api" by default

        # Train a few Q-values and set a known epsilon
        state = ("client_error", "HTTPError", 5, (), 1, 0, 0, False)
        learner.policy.update(state, ADD_PARAM, 9.9, state)
        learner.policy.epsilon = 0.123

        learner.save_policy()

        # New learner loading from the same dir
        learner2 = _make_learner(max_steps=3)
        learner2.base_dir = tmpdir
        learner2.load_policy()

        assert abs(learner2.policy.epsilon - 0.123) < 1e-6
        assert state in learner2.policy.q_table
        # Q-value updated by alpha=0.1: new_q = 0 + 0.1*(9.9 + 0.95*0 - 0) = 0.99
        assert learner2.policy.q_table[state][ADD_PARAM] > 0


def test_load_nonexistent_policy_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        learner = _make_learner()
        learner.base_dir = tmpdir  # no policy file exists yet
        # Should not raise; policy stays fresh
        learner.load_policy()
        assert learner.policy.q_table == {}


# ── CLIResultAdapter ──────────────────────────────────────────────────────────

cli_adapter = CLIResultAdapter()


def test_cli_result_adapter_success():
    ir = cli_adapter.adapt(0, "Created successfully", "")
    assert ir.success is True
    assert ir.status_category == "success"
    assert ir.error_class == "ExitCode_0"
    assert ir.output_text == "Created successfully"


def test_cli_result_adapter_failure():
    ir = cli_adapter.adapt(1, "", "Error: name is required")
    assert ir.success is False
    assert ir.status_category == "client_error"
    assert ir.error_class == "ExitCode_1"
    assert "name is required" in ir.output_text


# ── extract_validation_errors ────────────────────────────────────────────────


def test_extract_standard_errors_dict():
    fail_data = {
        "HTTPError": {
            "response": {
                "errors": {
                    "label": [
                        "cannot contain characters other than ascii alpha numerals",
                        "cannot contain more than 128 characters",
                    ],
                    "name": ["is required"],
                }
            }
        }
    }
    result = extract_validation_errors(fail_data)
    assert "label" in result
    assert len(result["label"]) == 2
    assert "name" in result
    assert result["name"] == ["is required"]


def test_extract_singular_error_key():
    fail_data = {"HTTPError": {"response": {"error": {"name": ["can't be blank"]}}}}
    result = extract_validation_errors(fail_data)
    assert result == {"name": ["can't be blank"]}


def test_extract_fastapi_detail():
    fail_data = {
        "HTTPError": {
            "response": {
                "detail": [
                    {"loc": ["body", "label"], "msg": "must be alphanumeric"},
                    {"loc": ["body", "name"], "msg": "too short"},
                ]
            }
        }
    }
    result = extract_validation_errors(fail_data)
    assert result == {"label": ["must be alphanumeric"], "name": ["too short"]}


def test_extract_no_validation_errors():
    fail_data = {"HTTPError": {"response": {"status": 500, "message": "Internal error"}}}
    assert extract_validation_errors(fail_data) == {}


def test_extract_non_http_error():
    fail_data = {"TypeError": ("unexpected type",)}
    assert extract_validation_errors(fail_data) == {}


def test_extract_empty_input():
    assert extract_validation_errors({}) == {}
    assert extract_validation_errors("not a dict") == {}


def test_extract_string_messages():
    fail_data = {"HTTPError": {"response": {"errors": {"label": "single string message"}}}}
    result = extract_validation_errors(fail_data)
    assert result == {"label": ["single string message"]}


# ── Validation errors in InteractionResult ───────────────────────────────────


def test_adapt_422_captures_validation_errors():
    result = {
        "fail": {
            "HTTPError": {
                "response": {
                    "errors": {"label": ["must be alphanumeric"]},
                    "status": 422,
                }
            }
        }
    }
    ir = adapter.adapt(result)
    assert ir.validation_errors == {"label": ["must be alphanumeric"]}


def test_adapt_non_422_has_empty_validation():
    result = {"fail": {"TypeError": ("bad type",)}}
    ir = adapter.adapt(result)
    assert ir.validation_errors == {}


def test_adapt_pass_has_empty_validation():
    result = {"pass": {"id": 1}}
    ir = adapter.adapt(result)
    assert ir.validation_errors == {}


# ── State encoding with has_validation ───────────────────────────────────────


def test_state_includes_has_validation_true():
    ir = _make_ir(validation_errors={"label": ["bad"]})
    genes = [["name"], ["gen_alphanumeric"]]
    key = encoder.encode(ir, genes, 0, 0, 0)
    assert key[-2] is True  # has_validation is second-to-last


def test_state_includes_has_validation_false():
    ir = _make_ir()
    genes = [["name"], ["gen_alphanumeric"]]
    key = encoder.encode(ir, genes, 0, 0, 0)
    assert key[-2] is False  # has_validation is second-to-last
    assert key[-1] is False  # has_missing is last


def test_validation_changes_state_key():
    genes = [["name"], ["gen_alphanumeric"]]
    ir_no_val = _make_ir()
    ir_with_val = _make_ir(validation_errors={"label": ["bad"]})
    k1 = encoder.encode(ir_no_val, genes, 0, 0, 0)
    k2 = encoder.encode(ir_with_val, genes, 0, 0, 0)
    assert k1 != k2


# ── TARGETED_SWAP action ────────────────────────────────────────────────────


# ── Targeted ADD_PARAM ───────────────────────────────────────────────────────


def test_targeted_add_adds_specific_params():
    genes = [["label"], ["gen_utf8"]]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE, add_params=["name"])
    assert "name" in result[0]
    assert len(result[0]) == 2
    assert len(result[1]) == 2
    idx = result[0].index("name")
    assert result[1][idx] in TYPE_POOLS["name"]


def test_targeted_add_multiple_params():
    genes = [[], []]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE, add_params=["name", "label"])
    assert "name" in result[0]
    assert "label" in result[0]
    assert len(result[0]) == len(result[1])


def test_targeted_add_skips_already_present():
    genes = [["name"], ["gen_utf8"]]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE, add_params=["name"])
    assert len(result[0]) == 1  # name already present, nothing added


def test_targeted_add_falls_back_to_random_without_params():
    genes = [["name"], ["gen_utf8"]]
    result = apply_action(genes, ADD_PARAM, TYPE_POOLS, AVAILABLE, add_params=[])
    # Falls back to random add — should add one of the unused params
    assert len(result[0]) == len(result[1])


def test_adapter_populates_missing_params():
    adapter = APIResultAdapter()
    result = {
        "fail": {
            "TypeError": (
                "Organization.__init__() missing 1 required positional argument: 'name'",
            )
        }
    }
    ir = adapter.adapt(result)
    assert ir.missing_params == ["name"]


def test_adapter_empty_missing_params_for_http_error():
    adapter = APIResultAdapter()
    result = {"fail": {"HTTPError": {"response": {"status": 422}}}}
    ir = adapter.adapt(result)
    assert ir.missing_params == []


def test_missing_params_override_forces_add():
    learner = _make_learner()
    ir = InteractionResult(
        success=False,
        output_text="missing 1 required positional argument: 'name'",
        status_category="client_error",
        error_class="TypeError",
        raw={},
        missing_params=["name"],
    )
    # Policy would normally pick NOOP with epsilon=0 on fresh state
    learner.policy.epsilon = 0.0
    action = learner._select_action_with_override(NOOP, ir)
    assert action == ADD_PARAM


def test_missing_params_override_takes_priority_over_validation():
    learner = _make_learner()
    ir = InteractionResult(
        success=False,
        output_text="missing arg and validation error",
        status_category="client_error",
        error_class="TypeError",
        raw={},
        validation_errors={"label": ["too long"]},
        missing_params=["name"],
    )
    learner.validation_override_prob = 1.0
    action = learner._select_action_with_override(TARGETED_SWAP, ir)
    # Missing params override wins over validation override
    assert action == ADD_PARAM


# ── TARGETED_SWAP action ────────────────────────────────────────────────────


def test_targeted_swap_uses_recommendation():
    genes = [["name", "label"], ["gen_utf8", "gen_utf8"]]
    recs = {"label": "gen_alphanumeric"}
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    assert result[0] == ["name", "label"]
    assert result[1][1] == "gen_alphanumeric"
    assert result[1][0] == "gen_utf8"  # untouched


def test_targeted_swap_degrades_without_recommendations():
    genes = [["name"], ["gen_alphanumeric"]]
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations={})
    # Falls back to NOOP when no recommendations apply
    assert result[0] == ["name"]
    assert result[1] == ["gen_alphanumeric"]


def test_targeted_swap_degrades_when_field_not_in_genes():
    genes = [["name"], ["gen_alphanumeric"]]
    recs = {"nonexistent_field": "gen_url"}
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    # Falls back to NOOP since no matching field
    assert result[0] == ["name"]
    assert result[1] == ["gen_alphanumeric"]


def test_targeted_swap_preserves_pairing():
    genes = [["name", "label", "description"], ["gen_utf8", "gen_utf8", "gen_utf8"]]
    recs = {"label": "gen_alphanumeric"}
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    assert len(result[0]) == len(result[1])
    assert len(result[0]) == 3


def test_targeted_swap_skips_same_generator():
    genes = [["label"], ["gen_alphanumeric"]]
    recs = {"label": "gen_alphanumeric"}  # same as current
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    # Falls back to NOOP since rec matches current
    assert result[0] == ["label"]
    assert result[1] == ["gen_alphanumeric"]


def test_targeted_swap_applies_multiple_fields():
    genes = [["name", "label"], ["gen_utf8", "gen_utf8"]]
    recs = {"name": "gen_uuid", "label": "gen_alphanumeric"}
    result = apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    assert result[1][0] == "gen_uuid"
    assert result[1][1] == "gen_alphanumeric"


def test_targeted_swap_does_not_mutate_input():
    genes = [["name", "label"], ["gen_utf8", "gen_utf8"]]
    original_0 = genes[0][:]
    original_1 = genes[1][:]
    recs = {"label": "gen_alphanumeric"}
    apply_action(genes, TARGETED_SWAP, TYPE_POOLS, AVAILABLE, field_recommendations=recs)
    assert genes[0] == original_0
    assert genes[1] == original_1


# ── GeneratorRecommenderNet ──────────────────────────────────────────────────


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_produces_valid_generator():
    from rizza.agentic_tester import GeneratorRecommenderNet

    gen_names = ["gen_alpha", "gen_alphanumeric", "gen_url", "gen_integer"]
    rec = GeneratorRecommenderNet(generator_names=gen_names, epsilon=1.0)
    name, score, embedding = rec.recommend("must be alphanumeric")
    assert name in gen_names
    import torch

    assert isinstance(embedding, torch.Tensor)


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_respects_type_pool():
    from rizza.agentic_tester import GeneratorRecommenderNet

    gen_names = ["gen_alpha", "gen_alphanumeric", "gen_url", "gen_integer"]
    rec = GeneratorRecommenderNet(generator_names=gen_names, epsilon=1.0)
    pool = ["gen_alpha", "gen_alphanumeric"]
    for _ in range(20):
        name, _, _ = rec.recommend("some validation error", type_pool=pool)
        assert name in pool


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_exploitation_mode():
    from rizza.agentic_tester import GeneratorRecommenderNet

    gen_names = ["gen_alpha", "gen_alphanumeric", "gen_url"]
    rec = GeneratorRecommenderNet(generator_names=gen_names, epsilon=0.0)
    name, score, _ = rec.recommend("must be a valid URL")
    assert name in gen_names
    assert isinstance(score, float)


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_update_stores_transition():
    from rizza.agentic_tester import GeneratorRecommenderNet

    gen_names = ["gen_alpha", "gen_alphanumeric", "gen_url"]
    rec = GeneratorRecommenderNet(generator_names=gen_names, epsilon=1.0, batch_size=2)
    _, _, emb = rec.recommend("some error")
    rec.update(emb, "gen_alpha", 5.0)
    assert len(rec.replay_buffer) == 1
    _, _, emb2 = rec.recommend("another error")
    rec.update(emb2, "gen_url", -2.0)
    assert len(rec.replay_buffer) == 2


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_save_load_roundtrip():
    import torch

    from rizza.agentic_tester import GeneratorRecommenderNet

    gen_names = ["gen_alpha", "gen_alphanumeric", "gen_url"]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "gen_rec.pt"
        rec = GeneratorRecommenderNet(generator_names=gen_names, epsilon=0.42)
        rec.save(path)

        rec2 = GeneratorRecommenderNet(generator_names=gen_names, epsilon=0.99)
        rec2.load(path)
        assert abs(rec2.epsilon - 0.42) < 1e-6

        for p1, p2 in zip(rec.q_net.parameters(), rec2.q_net.parameters(), strict=False):
            assert torch.allclose(p1, p2)


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_load_mismatched_generators():
    from rizza.agentic_tester import GeneratorRecommenderNet

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "gen_rec.pt"
        rec = GeneratorRecommenderNet(generator_names=["gen_alpha", "gen_url"], epsilon=0.42)
        rec.save(path)

        rec2 = GeneratorRecommenderNet(
            generator_names=["gen_alpha", "gen_url", "gen_integer"], epsilon=0.99
        )
        rec2.load(path)
        # Should NOT load since generator lists differ
        assert abs(rec2.epsilon - 0.99) < 1e-6


# ── Embedding encoder with has_validation ────────────────────────────────────


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_embedding_encoder_validation_changes_state():
    from rizza.agentic_tester import EmbeddingStateEncoder

    enc = EmbeddingStateEncoder()
    genes = [["name"], ["gen_alphanumeric"]]
    ir_no_val = InteractionResult(
        success=False,
        output_text="bad",
        status_category="client_error",
        error_class="HTTPError",
        raw={},
        validation_errors={},
    )
    ir_with_val = InteractionResult(
        success=False,
        output_text="bad",
        status_category="client_error",
        error_class="HTTPError",
        raw={},
        validation_errors={"label": ["must be alphanumeric"]},
    )
    s1 = enc.encode(ir_no_val, genes, 0, 0, 0)
    s2 = enc.encode(ir_with_val, genes, 0, 0, 0)
    # The last context element should differ (0.0 vs 1.0)
    assert s1[-1].item() == 0.0
    assert s2[-1].item() == 1.0


# ── Episode with TARGETED_SWAP ──────────────────────────────────────────────


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_episode_targeted_swap_with_validation():
    """Verify TARGETED_SWAP can be selected and uses recommender in an episode."""
    results_queue = [
        {
            "fail": {
                "HTTPError": {
                    "response": {
                        "errors": {"label": ["must be alphanumeric"]},
                        "status": 422,
                    }
                }
            }
        },
        {"pass": {"id": 99}},
    ]
    judge_map = {"pass": 500, "fail": -200}
    learner = _make_learner(results_queue=results_queue, judge_map=judge_map, max_steps=5)
    # Force epsilon=1.0 so TARGETED_SWAP will eventually be tried
    learner.policy.epsilon = 1.0

    org = _make_organism([["name", "label"], ["gen_utf8", "gen_utf8"]], points=-200)
    initial_result = {
        "fail": {
            "HTTPError": {
                "response": {
                    "errors": {"label": ["must be alphanumeric"]},
                    "status": 422,
                }
            }
        }
    }
    # Should not crash even if recommender is None (falls back to SWAP_INPUT)
    learner._run_episode(org, initial_result, {})
    # We can't guarantee improvement in a random test, just verify no crash


# ── Validation override (Fix A) ──────────────────────────────────────────────


def test_validation_override_forces_targeted_swap():
    """With override_prob=1.0, TARGETED_SWAP should always be chosen
    when validation errors are present (even with greedy policy)."""
    results_queue = [{"fail": {"TypeError": ("err",)}} for _ in range(10)]
    judge_map = {"TypeError": -200}
    learner = _make_learner(
        results_queue=results_queue,
        judge_map=judge_map,
        max_steps=1,
        validation_override_prob=1.0,
        validation_override_decay=1.0,
    )
    learner.policy.epsilon = 0.0  # greedy — would never randomly pick TARGETED_SWAP
    learner.gen_recommender = MagicMock()  # override requires a recommender to be present
    learner.gen_recommender.recommend.return_value = ("gen_alphanumeric", 1.0, MagicMock())

    ir_with_val = _make_ir(validation_errors={"label": ["bad"]})
    action = learner._select_action_with_override(ADD_PARAM, ir_with_val)
    assert action == TARGETED_SWAP

    # Now test the full episode path where the override takes effect
    org = _make_organism([["label"], ["gen_utf8"]], points=-200)
    initial_result = {
        "fail": {
            "HTTPError": {
                "response": {
                    "errors": {"label": ["must be alphanumeric"]},
                    "status": 422,
                }
            }
        }
    }
    learner._run_episode(org, initial_result, {})
    # The key assertion: override_prob should have decayed (decay=1.0, so stays at 1.0)
    assert learner.validation_override_prob == 1.0


def test_validation_override_does_not_fire_without_errors():
    """Override should not engage when there are no validation errors."""
    results_queue = [{"fail": {"TypeError": ("err",)}} for _ in range(10)]
    judge_map = {"TypeError": -200}
    learner = _make_learner(
        results_queue=results_queue,
        judge_map=judge_map,
        max_steps=2,
        validation_override_prob=1.0,
        validation_override_decay=1.0,
    )
    learner.policy.epsilon = 0.0

    # No validation errors in the initial result
    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    initial_result = {"fail": {"TypeError": ("bad type",)}}
    learner._run_episode(org, initial_result, {})
    # Should complete without errors; override doesn't interfere


def test_validation_override_decays_per_generation():
    """validation_override_prob should decrease once per learn_from_generation call."""
    results_queue = [{"fail": {"TypeError": ("err",)}} for _ in range(20)]
    judge_map = {"TypeError": -200}
    learner = _make_learner(
        results_queue=results_queue,
        judge_map=judge_map,
        max_steps=3,
        validation_override_prob=0.5,
        validation_override_decay=0.9,
    )

    org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
    initial_result = {"fail": {"TypeError": ("bad",)}}
    initial_prob = learner.validation_override_prob
    learner.learn_from_generation([(org, initial_result)], {})
    assert abs(learner.validation_override_prob - initial_prob * 0.9) < 1e-6


# ── Recommender batch_size from config (Fix B) ──────────────────────────────


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_batch_size_from_config():
    """Recommender should use the configured batch_size."""
    learner = _make_learner(recommender_batch_size=4)
    if learner.gen_recommender is not None:
        assert learner.gen_recommender.batch_size == 4


# ── Recommender per-episode epsilon decay (Fix C) ───────────────────────────


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_recommender_epsilon_decays_per_episode():
    """Recommender epsilon should decay after each episode, even without TARGETED_SWAP."""
    results_queue = [{"fail": {"TypeError": ("err",)}} for _ in range(10)]
    judge_map = {"TypeError": -200}
    learner = _make_learner(
        results_queue=results_queue,
        judge_map=judge_map,
        max_steps=2,
        validation_override_prob=0.0,  # disable override so TARGETED_SWAP won't fire
        recommender_epsilon_decay_per_episode=0.9,
    )
    learner.policy.epsilon = 0.0  # greedy, never picks TARGETED_SWAP

    if learner.gen_recommender is not None:
        initial_eps = learner.gen_recommender.epsilon
        org = _make_organism([["name"], ["gen_alphanumeric"]], points=-200)
        initial_result = {"fail": {"TypeError": ("bad type",)}}
        learner._run_episode(org, initial_result, {})
        assert learner.gen_recommender.epsilon < initial_eps
        expected = initial_eps * 0.9
        assert abs(learner.gen_recommender.epsilon - expected) < 1e-6


# ── Save/load persistence for validation_override_prob ──────────────────────


def test_save_load_preserves_validation_override_prob():
    with tempfile.TemporaryDirectory() as tmpdir:
        learner = _make_learner(max_steps=3, validation_override_prob=0.5)
        learner.base_dir = tmpdir
        learner.validation_override_prob = 0.123
        learner.save_policy()

        learner2 = _make_learner(max_steps=3, validation_override_prob=0.5)
        learner2.base_dir = tmpdir
        learner2.load_policy()
        assert abs(learner2.validation_override_prob - 0.123) < 1e-6


def test_load_old_checkpoint_uses_config_default():
    """Loading a checkpoint without validation_override_prob uses the config default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save an old-format checkpoint (no validation_override_prob)
        learner = _make_learner(max_steps=3)
        learner.base_dir = tmpdir
        learner.save_policy()
        # Manually strip the key from the saved file
        import json

        path = learner._policy_path()
        data = json.loads(path.read_text())
        data.pop("validation_override_prob", None)
        path.write_text(json.dumps(data))

        learner2 = _make_learner(max_steps=3, validation_override_prob=0.75)
        learner2.base_dir = tmpdir
        learner2.load_policy()
        assert abs(learner2.validation_override_prob - 0.75) < 1e-6
