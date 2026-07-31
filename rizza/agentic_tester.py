"""Post-generation RL exploitation phase for rizza's genetic algorithm."""
import ast
import importlib.util
import json
import logging
from pathlib import Path
import random

import attr

logger = logging.getLogger(__name__)

ADD_PARAM, DROP_PARAM, NOOP, TARGETED_SWAP = 0, 1, 2, 3

_TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def _deep_copy_genes(genes):
    return [genes[0][:], genes[1][:]]


from rizza.interface_adapter import (  # noqa: F401
    APIInterfaceAdapter,
    CLIInterfaceAdapter,
    InteractionResult,
)


class APIResultAdapter:
    """Backward-compatible wrapper around APIInterfaceAdapter.adapt_result()."""

    def adapt(self, result):
        return APIInterfaceAdapter().adapt_result(result)


class CLIResultAdapter:
    """Backward-compatible wrapper around CLIInterfaceAdapter.adapt_result()."""

    def adapt(self, exit_code, stdout, stderr):
        return CLIInterfaceAdapter().adapt_result(exit_code, stdout, stderr)


class CategoricalStateEncoder:
    """Encodes InteractionResult + gene context into a hashable state key."""

    def encode(self, interaction, genes, step, prev_points, curr_points):
        gene_len_bucket = min(len(genes[0]), 6) // 2  # 0, 1, 2, 3
        step_bucket = min(step, 5) // 2  # 0, 1, 2
        trend = 1 if curr_points > prev_points else (0 if curr_points == prev_points else -1)
        has_validation = bool(getattr(interaction, "validation_errors", None))
        has_missing = bool(getattr(interaction, "missing_params", None))
        validation_fields = tuple(sorted(getattr(interaction, "validation_errors", {}).keys()))
        error_text_bucket = hash(interaction.output_text) % 16
        return (
            interaction.status_category,
            interaction.error_class,
            error_text_bucket,
            validation_fields,
            gene_len_bucket,
            step_bucket,
            trend,
            has_validation,
            has_missing,
        )


# Module-level cache so recursive GeneticEntityTester instances share one loaded model.
_MODEL_CACHE = {}


def _load_hf_model(model_name, token):
    """Load (tokenizer, model) once per process, preferring the local cache."""
    import logging as _logging
    import warnings

    import torch
    from transformers import AutoModel, AutoTokenizer, logging as hf_logging

    cache_key = (model_name, token)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    for _noisy in ("transformers", "httpx", "huggingface_hub"):
        _logging.getLogger(_noisy).setLevel(_logging.WARNING)
    hf_logging.disable_progress_bar()
    warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")
    warnings.filterwarnings("ignore", message=".*unauthenticated.*")

    kwargs = {"token": token or None}
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True, **kwargs)
        model = AutoModel.from_pretrained(model_name, local_files_only=True, **kwargs)
    except Exception:
        tokenizer = AutoTokenizer.from_pretrained(model_name, **kwargs)
        model = AutoModel.from_pretrained(model_name, **kwargs)

    model.eval()
    _MODEL_CACHE[cache_key] = (tokenizer, model, torch)
    return _MODEL_CACHE[cache_key]


class EmbeddingStateEncoder:
    """Encodes InteractionResult into a dense state tensor using sentence embeddings."""

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2", token=None):
        self.tokenizer, self.model, self._torch = _load_hf_model(model_name, token)

    def _embed(self, text):
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=128,
        )
        with self._torch.no_grad():
            outputs = self.model(**inputs)
            return outputs.last_hidden_state.mean(dim=1).squeeze()

    def get_embedding(self, interaction):
        return self._embed(interaction.output_text)

    def encode(self, interaction, genes, step, prev_points, curr_points):
        embedding = self._embed(interaction.output_text)
        has_validation = float(bool(getattr(interaction, "validation_errors", None)))
        context = self._torch.tensor(
            [len(genes[0]), float(step), float(curr_points - prev_points), has_validation],
            dtype=self._torch.float32,
        )
        return self._torch.cat([embedding, context])


class QTablePolicy:
    """Tabular Q-learning with epsilon-greedy exploration."""

    def __init__(
        self,
        n_actions=4,
        alpha=0.1,
        gamma=0.95,
        epsilon=0.3,
        epsilon_decay=0.995,
        epsilon_min=0.05,
    ):
        self.q_table = {}
        self.n_actions = n_actions
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min

    def select_action(self, state_key):
        if random.random() < self.epsilon:
            return random.randrange(self.n_actions)
        q_values = self.q_table.get(state_key, [0.0] * self.n_actions)
        return max(range(self.n_actions), key=lambda a: q_values[a])

    def update(self, state_key, action, reward, next_state_key):
        if state_key not in self.q_table:
            self.q_table[state_key] = [0.0] * self.n_actions
        if next_state_key not in self.q_table:
            self.q_table[next_state_key] = [0.0] * self.n_actions
        current_q = self.q_table[state_key][action]
        max_next_q = max(self.q_table[next_state_key])
        self.q_table[state_key][action] = current_q + self.alpha * (
            reward + self.gamma * max_next_q - current_q
        )
        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)


class DQNPolicy:
    """Deep Q-Network with experience replay."""

    def __init__(
        self,
        state_dim=388,
        n_actions=4,
        hidden_dim=128,
        buffer_size=2000,
        batch_size=32,
        alpha=1e-3,
        gamma=0.95,
        epsilon=0.3,
        epsilon_decay=0.995,
        epsilon_min=0.05,
    ):
        import torch
        from torch import nn

        self._torch = torch
        self.device = torch.device("cpu")
        self.n_actions = n_actions
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min

        self.q_net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        ).to(self.device)

        self.optimizer = torch.optim.Adam(self.q_net.parameters(), lr=alpha)
        self.loss_fn = nn.SmoothL1Loss()
        self.replay_buffer = []
        self.buffer_size = buffer_size
        self.batch_size = batch_size

    def select_action(self, state_tensor):
        if random.random() < self.epsilon:
            return random.randrange(self.n_actions)
        with self._torch.no_grad():
            q_values = self.q_net(state_tensor.unsqueeze(0))
            return q_values.argmax(dim=1).item()

    def store_transition(self, state, action, reward, next_state, done):
        self.replay_buffer.append((state, action, reward, next_state, done))
        if len(self.replay_buffer) > self.buffer_size:
            self.replay_buffer.pop(0)

    def train_step(self):
        torch = self._torch
        if len(self.replay_buffer) < self.batch_size:
            return
        batch = random.sample(self.replay_buffer, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch, strict=False)
        states = torch.stack(states)
        next_states = torch.stack(next_states)
        actions = torch.tensor(actions, dtype=torch.long)
        rewards = torch.tensor(rewards, dtype=torch.float32)
        dones = torch.tensor(dones, dtype=torch.float32)
        current_q = self.q_net(states).gather(1, actions.unsqueeze(1)).squeeze()
        with torch.no_grad():
            max_next_q = self.q_net(next_states).max(dim=1).values
        target_q = rewards + self.gamma * max_next_q * (1 - dones)
        loss = self.loss_fn(current_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)

    # Q-table-compatible interface for AgenticPayloadLearner
    def update(self, state, action, reward, next_state):
        self.store_transition(state, action, reward, next_state, False)
        self.train_step()


class GeneratorRecommenderNet:
    """Contextual bandit that recommends generators based on validation messages.

    Uses a sentence-transformer embedding of the validation message as context
    and learns which generator types satisfy different validation constraints.
    """

    def __init__(
        self,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        token=None,
        generator_names=None,
        embedding_dim=384,
        hidden_dim=128,
        buffer_size=2000,
        batch_size=32,
        lr=1e-3,
        epsilon=0.3,
        epsilon_decay=0.995,
        epsilon_min=0.05,
    ):
        import torch
        from torch import nn

        self._torch = torch
        self.generator_names = list(generator_names or [])
        self.n_generators = len(self.generator_names)
        self._gen_to_idx = {name: i for i, name in enumerate(self.generator_names)}
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min

        self.tokenizer, self.model, _ = _load_hf_model(model_name, token)

        self.q_net = nn.Sequential(
            nn.Linear(embedding_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, self.n_generators),
        )
        self.q_net.eval()

        self.optimizer = torch.optim.Adam(self.q_net.parameters(), lr=lr)
        self.loss_fn = nn.SmoothL1Loss()
        self.replay_buffer = []
        self.buffer_size = buffer_size
        self.batch_size = batch_size

    def _embed(self, text):
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=128,
        )
        with self._torch.no_grad():
            outputs = self.model(**inputs)
            return outputs.last_hidden_state.mean(dim=1).squeeze()

    def recommend(self, validation_message, type_pool=None):
        """Recommend a generator for a validation message.

        Returns (generator_name, confidence_score). When type_pool is provided,
        only generators in the pool are considered.
        """
        embedding = self._embed(validation_message)

        if random.random() < self.epsilon:
            candidates = (
                [g for g in self.generator_names if g in type_pool]
                if type_pool
                else self.generator_names
            )
            if not candidates:
                candidates = self.generator_names
            chosen = random.choice(candidates)
            return chosen, 0.0, embedding

        with self._torch.no_grad():
            scores = self.q_net(embedding.unsqueeze(0)).squeeze()

        if type_pool:
            mask = self._torch.full_like(scores, float("-inf"))
            for g in type_pool:
                idx = self._gen_to_idx.get(g)
                if idx is not None:
                    mask[idx] = 0.0
            scores = scores + mask
            if (mask == float("-inf")).all():
                scores = self.q_net(embedding.unsqueeze(0)).squeeze()

        best_idx = scores.argmax().item()
        return self.generator_names[best_idx], scores[best_idx].item(), embedding

    def update(self, embedding, generator_name, reward):
        """Record an outcome and train on a mini-batch."""
        gen_idx = self._gen_to_idx.get(generator_name)
        if gen_idx is None:
            return

        self.replay_buffer.append((embedding.detach(), gen_idx, float(reward)))
        if len(self.replay_buffer) > self.buffer_size:
            self.replay_buffer.pop(0)

        self.epsilon = max(self.epsilon * self.epsilon_decay, self.epsilon_min)
        self._train_step()

    def _train_step(self):
        torch = self._torch
        if len(self.replay_buffer) < self.batch_size:
            return

        batch = random.sample(self.replay_buffer, self.batch_size)
        embeddings, actions, rewards = zip(*batch, strict=False)

        embeddings = torch.stack(embeddings)
        actions = torch.tensor(actions, dtype=torch.long)
        rewards = torch.tensor(rewards, dtype=torch.float32)

        self.q_net.train()
        predicted_q = self.q_net(embeddings).gather(1, actions.unsqueeze(1)).squeeze()
        loss = self.loss_fn(predicted_q, rewards)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self.q_net.eval()

    def save(self, path):
        self._torch.save(
            {
                "state_dict": self.q_net.state_dict(),
                "epsilon": self.epsilon,
                "generator_names": self.generator_names,
            },
            path,
        )

    def load(self, path):
        try:
            checkpoint = self._torch.load(path, map_location="cpu", weights_only=False)
            saved_names = checkpoint.get("generator_names", [])
            if saved_names == self.generator_names:
                self.q_net.load_state_dict(checkpoint["state_dict"])
                self.epsilon = checkpoint["epsilon"]
                logger.debug(f"Loaded generator recommender from {path}")
            else:
                logger.debug("Generator list changed, starting fresh recommender")
        except Exception as e:
            logger.debug(f"Could not load generator recommender from {path}: {e}")


def apply_action(
    genes,
    action_id,
    type_pools,
    available_params,
    field_recommendations=None,
    add_params=None,
    required_params=None,
):
    """Apply a discrete action to genes, returning a new 2-list.

    Invariant: len(result[0]) == len(result[1]). Length is preserved for NOOP,
    grown by at most one for ADD_PARAM, and shrunk by at most one (never below
    the input length, and never below 1 once non-empty) for DROP_PARAM.

    field_recommendations is an optional dict {field_name: generator_name}
    used by TARGETED_SWAP to make informed mutations based on validation errors.
    add_params is an optional list of param names to add (for targeted ADD_PARAM).
    """
    new_genes = _deep_copy_genes(genes)
    all_generators = [gen for pool in type_pools.values() for gen in pool]

    if action_id == ADD_PARAM:
        if add_params:
            for param in add_params:
                if param in available_params and param not in new_genes[0]:
                    pool = type_pools.get(param) or new_genes[1] or all_generators
                    if pool:
                        new_genes[0].append(param)
                        new_genes[1].append(random.choice(pool))
        else:
            unused = [p for p in available_params if p not in new_genes[0]]
            if unused:
                param = random.choice(unused)
                pool = type_pools.get(param) or new_genes[1] or all_generators
                if pool:
                    new_genes[0].append(param)
                    new_genes[1].append(random.choice(pool))

    elif action_id == DROP_PARAM:
        if len(new_genes[0]) > 1:
            removable = [
                i
                for i in range(len(new_genes[0]))
                if not required_params or new_genes[0][i] not in required_params
            ]
            if removable:
                idx = random.choice(removable)
                del new_genes[0][idx]
                del new_genes[1][idx]

    elif action_id == TARGETED_SWAP and field_recommendations and new_genes[0]:
        for field, gen_name in field_recommendations.items():
            if field in new_genes[0]:
                idx = new_genes[0].index(field)
                if gen_name != new_genes[1][idx]:
                    new_genes[1][idx] = gen_name

    # NOOP: return unchanged copy

    return new_genes


@attr.s()
class AgenticPayloadLearner:
    """Orchestrates post-generation RL exploitation of failed organisms."""

    config = attr.ib()
    judge_fn = attr.ib()
    genes_to_task_fn = attr.ib()
    type_pools = attr.ib()
    available_params = attr.ib()
    required_params = attr.ib(factory=set)
    seek_bad = attr.ib(default=False)
    base_dir = attr.ib(default=None)
    entity = attr.ib(default="")
    method = attr.ib(default="")
    interface = attr.ib(default="api")
    product = attr.ib(default="default")
    version = attr.ib(default="stream")

    def __attrs_post_init__(self):
        from rizza import interface_loader

        adapter = interface_loader.get_current()
        if adapter is not None:
            self.adapter = adapter
        else:
            from rizza.interface_adapter import APIInterfaceAdapter

            self.adapter = APIInterfaceAdapter()
        self.max_candidates = getattr(self.config, "max_candidates_per_generation", 5)
        self.max_steps = getattr(self.config, "max_steps_per_candidate", 5)
        self.use_embeddings = getattr(self.config, "use_embeddings", False)
        self.validation_override_prob = getattr(self.config, "validation_override_prob", 0.5)
        self.validation_override_decay = getattr(self.config, "validation_override_decay", 0.995)
        self._recommender_epsilon_decay_per_episode = getattr(
            self.config, "recommender_epsilon_decay_per_episode", 0.998
        )
        self.bucket_similarity_threshold = getattr(
            self.config, "bucket_similarity_threshold", 0.85
        )

        policy_cfg = getattr(self.config, "policy", None)
        policy_kwargs = (
            {
                "alpha": getattr(policy_cfg, "alpha", 0.1),
                "gamma": getattr(policy_cfg, "gamma", 0.95),
                "epsilon": getattr(policy_cfg, "epsilon", 0.3),
                "epsilon_decay": getattr(policy_cfg, "epsilon_decay", 0.995),
                "epsilon_min": getattr(policy_cfg, "epsilon_min", 0.05),
            }
            if policy_cfg
            else {}
        )

        model_name = getattr(
            self.config, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
        )
        hf_token = getattr(self.config, "hf_token", None) or None

        if self.use_embeddings:
            if not _TORCH_AVAILABLE:
                raise ImportError(
                    "Embedding-based agentic learning requires torch and transformers. "
                    "Install with: pip install rizza[agentic]"
                )
            self.encoder = EmbeddingStateEncoder(model_name, token=hf_token)
            self.policy = DQNPolicy(state_dim=388, n_actions=4, **policy_kwargs)
        else:
            self.encoder = CategoricalStateEncoder()
            self.policy = QTablePolicy(n_actions=4, **policy_kwargs)

        self.gen_recommender = None
        if _TORCH_AVAILABLE:
            try:
                generator_names = self._build_generator_list()
                rec_batch_size = getattr(self.config, "recommender_batch_size", 8)
                self.gen_recommender = GeneratorRecommenderNet(
                    model_name=model_name,
                    token=hf_token,
                    generator_names=generator_names,
                    epsilon=policy_kwargs.get("epsilon", 0.3),
                    epsilon_decay=policy_kwargs.get("epsilon_decay", 0.995),
                    epsilon_min=policy_kwargs.get("epsilon_min", 0.05),
                    batch_size=rec_batch_size,
                )
            except Exception as e:
                logger.debug(f"Could not initialize generator recommender: {e}")

        self.load_policy()

    def _build_generator_list(self):
        """Build the list of generator names for the recommender output space."""
        try:
            from rizza.entity_tester import EntityTester

            all_methods = EntityTester.pull_input_methods()
            return sorted(
                name
                for name in all_methods
                if (not name.startswith("genetic") or name == "genetic_index")
                and not name.startswith("_")
            )
        except Exception:
            return sorted(
                set(
                    gen
                    for pool in self.type_pools.values()
                    for gen in pool
                    if not gen.startswith("genetic") or gen == "genetic_index"
                )
            )

    def _policy_path(self):
        if not self.base_dir:
            return None
        ext = "dqn.pt" if self.use_embeddings else "qtable.json"
        d = (
            Path(self.base_dir)
            / "data"
            / "agentic"
            / f"{self.product}-{self.version}"
            / self.interface
        )
        d.mkdir(parents=True, exist_ok=True)
        return d / ext

    def _recommender_path(self):
        if not self.base_dir:
            return None
        d = (
            Path(self.base_dir)
            / "data"
            / "agentic"
            / f"{self.product}-{self.version}"
            / self.interface
        )
        d.mkdir(parents=True, exist_ok=True)
        return d / "gen_recommender.pt"

    def load_policy(self):
        path = self._policy_path()
        if path is not None and path.exists():
            try:
                if self.use_embeddings:
                    import torch

                    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
                    self.policy.q_net.load_state_dict(checkpoint["state_dict"])
                    self.policy.epsilon = checkpoint["epsilon"]
                    self.validation_override_prob = checkpoint.get(
                        "validation_override_prob", self.validation_override_prob
                    )
                else:
                    data = json.loads(path.read_text())
                    loaded_table = {ast.literal_eval(k): v for k, v in data["q_table"].items()}
                    incompatible = any(
                        len(v) != self.policy.n_actions for v in loaded_table.values()
                    )
                    if incompatible:
                        logger.warning(
                            f"Saved Q-table has wrong action count "
                            f"(expected {self.policy.n_actions}); starting fresh"
                        )
                    else:
                        self.policy.q_table = loaded_table
                    self.policy.epsilon = data["epsilon"]
                    self.validation_override_prob = data.get(
                        "validation_override_prob", self.validation_override_prob
                    )
                logger.debug(f"Loaded agentic policy from {path}")
            except Exception as e:
                logger.debug(f"Could not load agentic policy from {path}: {e}")

        rec_path = self._recommender_path()
        if rec_path is not None and rec_path.exists() and self.gen_recommender is not None:
            self.gen_recommender.load(rec_path)

    def save_policy(self):
        path = self._policy_path()
        if path is not None:
            try:
                if self.use_embeddings:
                    import torch

                    torch.save(
                        {
                            "epsilon": self.policy.epsilon,
                            "state_dict": self.policy.q_net.state_dict(),
                            "validation_override_prob": self.validation_override_prob,
                        },
                        path,
                    )
                else:
                    data = {
                        "epsilon": self.policy.epsilon,
                        "q_table": {str(k): v for k, v in self.policy.q_table.items()},
                        "validation_override_prob": self.validation_override_prob,
                    }
                    path.write_text(json.dumps(data))
                logger.debug(f"Saved agentic policy to {path}")
            except Exception as e:
                logger.warning(f"Could not save agentic policy to {path}: {e}")

        rec_path = self._recommender_path()
        if rec_path is not None and self.gen_recommender is not None:
            try:
                self.gen_recommender.save(rec_path)
                logger.debug(f"Saved generator recommender to {rec_path}")
            except Exception as e:
                logger.warning(f"Could not save generator recommender to {rec_path}: {e}")

    def learn_from_generation(self, org_results, fitness_cache):
        """Run RL episodes on elite candidates from this generation.

        Returns list of (organism, new_genes, new_points, new_result) for improvements only.
        """
        buckets = self._bucket_organisms(org_results)
        elites = self._select_elites(buckets)
        improvements = []
        for organism, initial_result in elites:
            outcome = self._run_episode(organism, initial_result, fitness_cache)
            if outcome is not None:
                new_genes, new_points, new_result = outcome
                improvements.append((organism, new_genes, new_points, new_result))
        if elites:
            self.validation_override_prob = max(
                self.validation_override_prob * self.validation_override_decay, 0.1
            )
            self.save_policy()
        return improvements

    def _bucket_organisms(self, org_results):
        """Group organisms by error signature (Tier 1: string-key bucketing)."""
        if self.use_embeddings:
            return self._bucket_organisms_embedding(org_results)

        buckets = {}
        for organism, result in org_results:
            interaction = self.adapter.adapt_result(result)
            if interaction.success:
                continue
            if interaction.status_category == "server_error":
                continue
            key = (
                interaction.status_category,
                interaction.error_class,
                hash(interaction.output_text) % 16,
            )
            buckets.setdefault(key, []).append((organism, result))
        return buckets

    def _bucket_organisms_embedding(self, org_results):
        """Group organisms by embedding cosine similarity (Tier 2)."""
        import torch.nn.functional as F

        items = []
        for organism, result in org_results:
            interaction = self.adapter.adapt_result(result)
            if interaction.success or interaction.status_category == "server_error":
                continue
            embedding = self.encoder.get_embedding(interaction)
            items.append((organism, result, embedding))

        buckets = []
        for org, res, emb in items:
            placed = False
            for bucket in buckets:
                centroid = bucket["centroid"]
                similarity = F.cosine_similarity(emb.unsqueeze(0), centroid.unsqueeze(0)).item()
                if similarity > self.bucket_similarity_threshold:
                    bucket["members"].append((org, res))
                    n = len(bucket["members"])
                    bucket["centroid"] = centroid + (emb - centroid) / n
                    placed = True
                    break
            if not placed:
                buckets.append({"centroid": emb, "members": [(org, res)]})

        return {i: b["members"] for i, b in enumerate(buckets)}

    def _select_elites(self, buckets):
        """Select one elite per bucket (fittest or least-fit for seek_bad), capped."""
        elites = []
        for members in buckets.values():
            best = (min if self.seek_bad else max)(members, key=lambda m: m[0].points)
            elites.append(best)
        elites.sort(key=lambda e: e[0].points, reverse=not self.seek_bad)
        return elites[: self.max_candidates]

    def _select_action_with_override(self, action, interaction):
        """Override action selection based on error diagnostics.

        Missing params take priority — the method can't even be called without them.
        """
        if action != ADD_PARAM and getattr(interaction, "missing_params", None):
            return ADD_PARAM
        if (
            action != TARGETED_SWAP
            and interaction.validation_errors
            and self.gen_recommender is not None
            and random.random() < self.validation_override_prob
        ):
            return TARGETED_SWAP
        return action

    def _build_field_recommendations(self, action, current_genes, interaction):
        """Build field recommendations for TARGETED_SWAP based on validation errors."""
        field_recommendations = {}
        rec_embeddings = {}
        if (
            action != TARGETED_SWAP
            or self.gen_recommender is None
            or not interaction.validation_errors
        ):
            return field_recommendations, rec_embeddings
        for field, messages in interaction.validation_errors.items():
            if field not in current_genes[0]:
                continue
            for msg in messages:
                pool = self.type_pools.get(field)
                gen_name, _, embedding = self.gen_recommender.recommend(msg, type_pool=pool)
                field_recommendations[field] = gen_name
                rec_embeddings[field] = (embedding, gen_name, msg)
                break
        return field_recommendations, rec_embeddings

    def _run_episode(self, organism, initial_result, fitness_cache):
        """Run a bounded RL episode on one elite candidate.

        Returns (new_genes, new_points, new_result) if improved, else None.
        """
        reward_cfg = getattr(self.config, "reward", None)
        r_success = getattr(reward_cfg, "success", 20)
        r_improved = getattr(reward_cfg, "improved", 5)
        r_new_error = getattr(reward_cfg, "new_error", 3)
        r_same = getattr(reward_cfg, "same", -1)
        r_regressed = getattr(reward_cfg, "regressed", -2)
        r_server = getattr(reward_cfg, "server_error", -5)
        r_targeted = getattr(reward_cfg, "targeted_success", 8)

        current_genes = _deep_copy_genes(organism.genes)
        current_interaction = self.adapter.adapt_result(initial_result)
        current_points = organism.points
        baseline_genes = _deep_copy_genes(current_genes)
        best_genes = _deep_copy_genes(current_genes)
        best_points = current_points
        best_result = initial_result
        prev_points = current_points

        for step in range(self.max_steps):
            state = self.encoder.encode(
                current_interaction, current_genes, step, prev_points, current_points
            )
            action = self.policy.select_action(state)
            action = self._select_action_with_override(action, current_interaction)
            field_recommendations, rec_embeddings = self._build_field_recommendations(
                action, current_genes, current_interaction
            )

            add_params = []
            if action == ADD_PARAM and getattr(current_interaction, "missing_params", None):
                add_params = [
                    p
                    for p in current_interaction.missing_params
                    if p in self.available_params and p not in current_genes[0]
                ]

            next_genes = apply_action(
                current_genes,
                action,
                self.type_pools,
                self.available_params,
                field_recommendations=field_recommendations,
                add_params=add_params,
                required_params=self.required_params,
            )

            gene_key = str(next_genes)
            if gene_key in fitness_cache:
                result, points = fitness_cache[gene_key]
            else:
                task = self.genes_to_task_fn(next_genes)
                try:
                    result = task.execute()
                except RecursionError:
                    result = {"fail": {"RecursionError": ("max depth exceeded",)}}
                points = self.judge_fn(result)
                fitness_cache[gene_key] = (result, points)

            next_interaction = self.adapter.adapt_result(result)

            if next_interaction.success:
                reward = float(r_success)
                done = True
            elif next_interaction.status_category == "server_error":
                reward = float(r_server)
                done = False
                next_genes = _deep_copy_genes(baseline_genes)
                points = current_points
            elif points > current_points:
                reward = float(r_improved)
                done = False
                if (action == TARGETED_SWAP and field_recommendations) or (
                    action == ADD_PARAM and add_params
                ):
                    reward = float(r_targeted)
            elif next_interaction.error_class != current_interaction.error_class:
                reward = float(r_new_error)
                done = False
            elif points < current_points:
                reward = float(r_regressed)
                done = False
            else:
                reward = float(r_same)
                done = False

            next_state = self.encoder.encode(
                next_interaction, next_genes, step + 1, current_points, points
            )
            self.policy.update(state, action, reward, next_state)

            # Update the generator recommender with the observed reward
            if action == TARGETED_SWAP and rec_embeddings and self.gen_recommender is not None:
                for embedding, gen_name, _msg in rec_embeddings.values():
                    self.gen_recommender.update(embedding, gen_name, reward)

            if points > best_points:
                best_genes = _deep_copy_genes(next_genes)
                best_points = points
                best_result = result

            if next_interaction.status_category != "server_error" and points >= current_points:
                baseline_genes = _deep_copy_genes(next_genes)

            if done:
                break

            prev_points = current_points
            current_genes = next_genes
            current_points = points
            current_interaction = next_interaction

        # Decay recommender epsilon per-episode, independent of TARGETED_SWAP selection
        if self.gen_recommender is not None:
            self.gen_recommender.epsilon = max(
                self.gen_recommender.epsilon * self._recommender_epsilon_decay_per_episode,
                self.gen_recommender.epsilon_min,
            )

        if best_points > organism.points:
            return best_genes, best_points, best_result
        return None
