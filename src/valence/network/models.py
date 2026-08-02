from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from valence.config import (
    LatencyComponentConfig,
    LatencyPairConfig,
    NetworkConfig,
    ShockConfig,
)
from valence.network.distributions import (
    component_descriptor,
    latency_as_component,
    sample_component_ms,
    sample_quantile_latency_ms,
    sample_spliced_ms,
    theoretical_quantiles,
    stationary_distribution,
)


@dataclass
class EdgeState:
    jitter_ms: float = 0.0
    bad: bool = False
    latency_state: int | None = None
    latency_state_run_length: int = 0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def _pair_component(pair: LatencyPairConfig) -> LatencyComponentConfig:
    return LatencyComponentConfig(
        family=pair.distribution,
        calibration_mode=pair.calibration_mode,
        fixed_ms=pair.fixed_ms,
        shift_ms=pair.shift_ms,
        mean_ms=pair.mean_ms,
        sigma=pair.sigma,
        stddev_ms=pair.stddev_ms,
        shape=pair.shape,
        scale_ms=pair.scale_ms,
        erlang_stages=pair.erlang_stages,
        p50_ms=pair.p50_ms,
        p95_ms=pair.p95_ms,
        p99_ms=pair.p99_ms,
        max_ms=pair.max_ms,
        empirical_samples_ms=pair.samples_ms,
    )


class NetworkModel:
    def __init__(
        self,
        config: NetworkConfig,
        latency_rng: np.random.Generator,
        loss_rng: np.random.Generator,
    ):
        self.config = config
        self.latency_rng = latency_rng
        self.loss_rng = loss_rng
        self.edge_states: dict[tuple[int, int], EdgeState] = {}
        self.transmissions = 0
        self.drops = 0
        self.transmissions_by_region_pair: Counter[str] = Counter()
        self.drops_by_region_pair: Counter[str] = Counter()
        self.base_samples_by_region_pair: dict[str, list[float]] = defaultdict(list)
        self.effective_samples_by_region_pair: dict[str, list[float]] = defaultdict(list)
        self.latency_state_samples: Counter[str] = Counter()
        self.latency_state_transitions: Counter[str] = Counter()
        self.latency_state_run_lengths: dict[str, list[int]] = defaultdict(list)
        self.latency_component_samples: Counter[str] = Counter()
        self._global_latency_state = EdgeState()
        self._stationary_probabilities = (
            stationary_distribution(config.latency.transition_matrix)
            if config.latency.distribution == "markov_modulated"
            and config.latency.stationary_initialization
            else None
        )
        self._pairs = {
            (pair.source_region, pair.target_region): pair
            for pair in config.latency.pairs
        }

    @staticmethod
    def _pair_label(source_region: str, target_region: str) -> str:
        return f"{source_region}->{target_region}"

    def _state(self, source: int, target: int) -> EdgeState:
        return self.edge_states.setdefault((source, target), EdgeState())

    def active_shocks(
        self,
        time_ms: int,
        source_region: str,
        target_region: str,
    ) -> list[ShockConfig]:
        return [
            shock for shock in self.config.shocks
            if shock.start_ms <= time_ms < shock.end_ms
            and shock.region in {source_region, target_region}
        ]

    def _latency_pair(
        self,
        source_region: str,
        target_region: str,
    ) -> LatencyPairConfig | None:
        exact = self._pairs.get((source_region, target_region))
        if exact is not None:
            return exact
        if self.config.latency.profile_symmetric:
            return self._pairs.get((target_region, source_region))
        return None

    def _sample_markov_latency(self, source: int, target: int) -> float:
        latency = self.config.latency
        state = (
            self._global_latency_state
            if latency.markov_scope == "global"
            else self._state(source, target)
        )
        if state.latency_state is None:
            if self._stationary_probabilities is not None:
                state.latency_state = int(
                    self.latency_rng.choice(
                        len(latency.states), p=self._stationary_probabilities
                    )
                )
            else:
                state.latency_state = latency.initial_state
        current_index = state.latency_state
        current = latency.states[current_index]
        state.latency_state_run_length += 1
        self.latency_state_samples[current.name] += 1
        sampled = sample_component_ms(self.latency_rng, current.component)
        probabilities = np.asarray(latency.transition_matrix[current_index], dtype=float)
        next_index = int(self.latency_rng.choice(len(latency.states), p=probabilities))
        next_name = latency.states[next_index].name
        self.latency_state_transitions[f"{current.name}->{next_name}"] += 1
        if next_index != current_index:
            self.latency_state_run_lengths[current.name].append(
                state.latency_state_run_length
            )
            state.latency_state_run_length = 0
        state.latency_state = next_index
        return sampled

    def _sample_mixture_latency(self) -> float:
        latency = self.config.latency
        weights = np.asarray([component.weight for component in latency.components], dtype=float)
        weights = weights / weights.sum()
        index = int(self.latency_rng.choice(len(latency.components), p=weights))
        component = latency.components[index]
        label = component.name or f"component_{index}"
        self.latency_component_samples[label] += 1
        return sample_component_ms(self.latency_rng, component)

    def _sample_base_latency(
        self,
        source: int,
        target: int,
        source_region: str,
        target_region: str,
    ) -> float:
        latency = self.config.latency
        if latency.distribution == "regional_profile":
            pair = self._latency_pair(source_region, target_region)
            if pair is None:
                return sample_quantile_latency_ms(
                    self.latency_rng,
                    latency.p50_ms,
                    latency.p95_ms,
                    latency.p99_ms,
                    latency.max_ms,
                )
            if pair.mode == "empirical":
                return float(self.latency_rng.choice(pair.samples_ms))
            if pair.mode == "distribution":
                return sample_component_ms(self.latency_rng, _pair_component(pair))
            return sample_quantile_latency_ms(
                self.latency_rng,
                pair.p50_ms,
                pair.p95_ms,
                pair.p99_ms,
                pair.max_ms,
            )
        if latency.distribution == "spliced":
            return sample_spliced_ms(self.latency_rng, latency)
        if latency.distribution == "markov_modulated":
            return self._sample_markov_latency(source, target)
        if latency.distribution == "mixture":
            return self._sample_mixture_latency()
        return sample_component_ms(self.latency_rng, latency_as_component(latency))

    def sample_latency_ms(
        self,
        source: int,
        target: int,
        time_ms: int,
        source_region: str,
        target_region: str,
    ) -> int:
        base = self._sample_base_latency(
            source, target, source_region, target_region
        )
        pair_label = self._pair_label(source_region, target_region)
        self.base_samples_by_region_pair[pair_label].append(base)

        latency = self.config.latency
        state = self._state(source, target)
        innovation = float(self.latency_rng.normal(0.0, latency.jitter_sigma_ms))
        state.jitter_ms = latency.jitter_phi * state.jitter_ms + innovation
        delay = max(0.0, base + state.jitter_ms)

        for shock in self.active_shocks(time_ms, source_region, target_region):
            delay *= shock.latency_multiplier
        self.effective_samples_by_region_pair[pair_label].append(delay)
        return max(1, int(round(delay)))

    def is_dropped(
        self,
        source: int,
        target: int,
        time_ms: int,
        source_region: str,
        target_region: str,
    ) -> bool:
        loss = self.config.loss
        state = self._state(source, target)
        if loss.model == "none":
            probability = 0.0
        elif loss.model == "bernoulli":
            probability = loss.probability
        else:
            if state.bad:
                if self.loss_rng.random() < loss.bad_to_good:
                    state.bad = False
            elif self.loss_rng.random() < loss.good_to_bad:
                state.bad = True
            probability = loss.loss_bad if state.bad else loss.loss_good

        for shock in self.active_shocks(time_ms, source_region, target_region):
            probability += shock.loss_addition
        probability = min(1.0, max(0.0, probability))
        dropped = bool(self.loss_rng.random() < probability)
        label = self._pair_label(source_region, target_region)
        self.transmissions += 1
        self.transmissions_by_region_pair[label] += 1
        self.drops += int(dropped)
        self.drops_by_region_pair[label] += int(dropped)
        return dropped

    def transmit(
        self,
        source: int,
        target: int,
        time_ms: int,
        source_region: str,
        target_region: str,
    ) -> int | None:
        if self.is_dropped(source, target, time_ms, source_region, target_region):
            return None
        return time_ms + self.sample_latency_ms(
            source, target, time_ms, source_region, target_region
        )

    def _pair_target(
        self,
        pair: LatencyPairConfig | None,
    ) -> dict[str, object]:
        latency = self.config.latency
        if pair is not None and pair.mode == "quantiles":
            return {
                "mode": "quantiles",
                "family": "quantile_piecewise",
                "p50_ms": pair.p50_ms,
                "p95_ms": pair.p95_ms,
                "p99_ms": pair.p99_ms,
                "max_ms": pair.max_ms,
            }
        if pair is not None and pair.mode == "empirical":
            return self._empirical_target(pair.samples_ms)
        if pair is not None:
            component = _pair_component(pair)
            return {
                "mode": "distribution",
                **component_descriptor(component),
                **theoretical_quantiles(component),
            }
        if latency.distribution == "regional_profile":
            return {
                "mode": "fallback_quantiles",
                "family": "quantile_piecewise",
                "p50_ms": latency.p50_ms,
                "p95_ms": latency.p95_ms,
                "p99_ms": latency.p99_ms,
                "max_ms": latency.max_ms,
            }
        if latency.distribution == "spliced":
            return {
                "mode": "spliced",
                "splice_quantile": latency.splice_quantile,
                "body": component_descriptor(latency.body) if latency.body else {},
                "tail": component_descriptor(latency.tail) if latency.tail else {},
            }
        if latency.distribution == "markov_modulated":
            return {
                "mode": "markov_modulated",
                "initial_state": latency.initial_state,
                "stationary_initialization": latency.stationary_initialization,
                "markov_scope": latency.markov_scope,
                "stationary_probabilities": (
                    [round(float(value), 12) for value in self._stationary_probabilities]
                    if self._stationary_probabilities is not None
                    else []
                ),
                "states": [
                    {
                        "name": state.name,
                        "component": component_descriptor(state.component),
                    }
                    for state in latency.states
                ],
                "transition_matrix": [list(row) for row in latency.transition_matrix],
            }
        component = latency_as_component(latency)
        return {
            "mode": "distribution",
            **component_descriptor(component),
            **theoretical_quantiles(component),
        }

    def calibration_summary(self) -> dict[str, object]:
        latency = self.config.latency
        per_pair: dict[str, object] = {}
        labels = sorted(
            set(self.base_samples_by_region_pair)
            | set(self.transmissions_by_region_pair)
        )
        for label in labels:
            source_region, target_region = label.split("->", 1)
            pair = self._latency_pair(source_region, target_region)
            target = self._pair_target(pair)
            base = self.base_samples_by_region_pair.get(label, [])
            effective = self.effective_samples_by_region_pair.get(label, [])
            observed = self._quantile_dict(base)
            target_quantiles = {
                key: value for key, value in target.items()
                if key in {"p50_ms", "p95_ms", "p99_ms", "p999_ms"}
                and isinstance(value, (int, float))
            }
            errors = {
                f"{key}_absolute_error_ms": round(observed[key] - float(target_value), 6)
                for key, target_value in target_quantiles.items()
                if key in observed
            }
            transmissions = self.transmissions_by_region_pair.get(label, 0)
            drops = self.drops_by_region_pair.get(label, 0)
            per_pair[label] = {
                "target": target,
                "observed_base": observed,
                "observed_effective": self._quantile_dict(effective),
                "calibration_error": errors,
                "samples": len(base),
                "transmissions": transmissions,
                "drops": drops,
                "drop_rate": round(drops / transmissions, 12) if transmissions else 0.0,
            }
        all_base = [
            value for values in self.base_samples_by_region_pair.values() for value in values
        ]
        all_effective = [
            value for values in self.effective_samples_by_region_pair.values() for value in values
        ]
        total_states = sum(self.latency_state_samples.values())
        state_occupancy = {
            name: round(count / total_states, 12) if total_states else 0.0
            for name, count in sorted(self.latency_state_samples.items())
        }
        run_lengths = {name: list(values) for name, values in self.latency_state_run_lengths.items()}
        if latency.distribution == "markov_modulated":
            states_to_summarize = list(self.edge_states.values())
            if latency.markov_scope == "global":
                states_to_summarize.append(self._global_latency_state)
            for edge_state in states_to_summarize:
                if edge_state.latency_state is None or edge_state.latency_state_run_length <= 0:
                    continue
                name = latency.states[edge_state.latency_state].name
                run_lengths.setdefault(name, []).append(edge_state.latency_state_run_length)
        state_run_summary = {
            name: {
                "runs": len(values),
                "mean_run_length": round(float(np.mean(values)), 12) if values else 0.0,
                "p95_run_length": round(_percentile([float(v) for v in values], 0.95), 6) if values else 0.0,
                "max_run_length": max(values, default=0),
            }
            for name, values in sorted(run_lengths.items())
        }
        total_transitions = sum(self.latency_state_transitions.values())
        same_transitions = sum(
            count
            for label, count in self.latency_state_transitions.items()
            if label.split("->", 1)[0] == label.split("->", 1)[1]
        )
        total_components = sum(self.latency_component_samples.values())
        component_occupancy = {
            name: round(count / total_components, 12) if total_components else 0.0
            for name, count in sorted(self.latency_component_samples.items())
        }
        return {
            "latency_distribution": latency.distribution,
            "latency_model": self._pair_target(None),
            "latency_profile_name": latency.profile_name,
            "latency_profile_source": latency.profile_source,
            "latency_profile_symmetric": latency.profile_symmetric,
            "latency_profile_pair_count": len(latency.pairs),
            "attempted_base_latency": self._quantile_dict(all_base),
            "attempted_effective_latency": self._quantile_dict(all_effective),
            "attempted_latency_samples": len(all_base),
            "latency_state_occupancy": state_occupancy,
            "latency_state_transition_counts": dict(sorted(self.latency_state_transitions.items())),
            "latency_state_same_transition_rate": (
                round(same_transitions / total_transitions, 12) if total_transitions else 0.0
            ),
            "latency_state_run_summary": state_run_summary,
            "latency_component_occupancy": component_occupancy,
            "region_pair_latency": per_pair,
        }

    @staticmethod
    def _quantile_dict(values: list[float]) -> dict[str, float]:
        if not values:
            return {
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "p999_ms": 0.0,
            }
        return {
            "p50_ms": round(_percentile(values, 0.50), 6),
            "p95_ms": round(_percentile(values, 0.95), 6),
            "p99_ms": round(_percentile(values, 0.99), 6),
            "p999_ms": round(_percentile(values, 0.999), 6),
        }

    @classmethod
    def _empirical_target(cls, samples: tuple[float, ...]) -> dict[str, float | str]:
        values = list(samples)
        return {"mode": "empirical", "family": "empirical", **cls._quantile_dict(values)}
