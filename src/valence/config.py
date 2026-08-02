from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


BASE_LATENCY_FAMILIES = {
    "fixed",
    "shifted_exponential",
    "truncated_normal",
    "gamma",
    "erlang",
    "lognormal",
    "weibull",
    "loglogistic",
    "lomax",
    "generalized_pareto",
    "quantile",
    "quantile_piecewise",
    "empirical",
}
COMPOSITE_LATENCY_FAMILIES = {"mixture", "spliced", "markov_modulated"}
TOP_LEVEL_LATENCY_FAMILIES = BASE_LATENCY_FAMILIES | COMPOSITE_LATENCY_FAMILIES | {
    "regional_profile"
}


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 1
    slots: int = 8
    record_events: bool = True


@dataclass(frozen=True)
class ValidatorConfig:
    count: int = 32
    regions: tuple[str, ...] = ("north_america", "europe", "asia")
    region_assignment: str = "round_robin"
    region_weights: tuple[float, ...] = ()
    isps: tuple[str, ...] = ("isp_a", "isp_b", "isp_c")
    isp_assignment: str = "round_robin"
    isp_weights: tuple[float, ...] = ()
    stake_distribution: str = "equal"
    stake_sigma: float = 1.0
    explicit_stakes: tuple[float, ...] = ()


@dataclass(frozen=True)
class TopologyConfig:
    kind: str = "ring_plus_random"
    degree: int = 4
    same_region_bias: float = 0.8
    same_isp_bias: float = 0.0
    minimum_cross_region_peers: int = 1


@dataclass(frozen=True)
class LatencyComponentConfig:
    """A reusable latency-distribution component.

    `calibration_mode="p50_p95"` is supported for lognormal, Weibull,
    log-logistic, Lomax, and generalized Pareto families. Other families use
    their explicit parameters. Quantile-piecewise sampling uses all three
    supplied anchors exactly as model quantiles.
    """

    family: str = "quantile_piecewise"
    name: str = ""
    weight: float = 1.0
    calibration_mode: str = "parameters"
    fixed_ms: float = 50.0
    shift_ms: float = 0.0
    mean_ms: float = 80.0
    sigma: float = 0.55
    stddev_ms: float = 20.0
    shape: float = 2.0
    scale_ms: float = 50.0
    erlang_stages: int = 2
    p50_ms: float = 50.0
    p95_ms: float = 100.0
    p99_ms: float = 200.0
    max_ms: float = 0.0
    empirical_samples_ms: tuple[float, ...] = ()
    components: tuple["LatencyComponentConfig", ...] = ()


@dataclass(frozen=True)
class LatencyStateConfig:
    name: str
    component: LatencyComponentConfig = field(default_factory=LatencyComponentConfig)


@dataclass(frozen=True)
class LatencyPairConfig:
    source_region: str
    target_region: str
    mode: str = "quantiles"
    distribution: str = "quantile_piecewise"
    calibration_mode: str = "parameters"
    p50_ms: float = 50.0
    p95_ms: float = 100.0
    p99_ms: float = 200.0
    max_ms: float = 0.0
    fixed_ms: float = 50.0
    shift_ms: float = 0.0
    mean_ms: float = 80.0
    sigma: float = 0.55
    stddev_ms: float = 20.0
    shape: float = 2.0
    scale_ms: float = 50.0
    erlang_stages: int = 2
    samples_ms: tuple[float, ...] = ()


@dataclass(frozen=True)
class LatencyConfig:
    distribution: str = "fixed"
    calibration_mode: str = "parameters"
    fixed_ms: float = 50.0
    shift_ms: float = 0.0
    mean_ms: float = 80.0
    sigma: float = 0.55
    stddev_ms: float = 20.0
    shape: float = 2.0
    scale_ms: float = 50.0
    erlang_stages: int = 2
    jitter_phi: float = 0.0
    jitter_sigma_ms: float = 0.0
    p50_ms: float = 50.0
    p95_ms: float = 100.0
    p99_ms: float = 200.0
    max_ms: float = 0.0
    empirical_samples_ms: tuple[float, ...] = ()
    components: tuple[LatencyComponentConfig, ...] = ()
    body: LatencyComponentConfig | None = None
    tail: LatencyComponentConfig | None = None
    splice_quantile: float = 0.99
    states: tuple[LatencyStateConfig, ...] = ()
    transition_matrix: tuple[tuple[float, ...], ...] = ()
    initial_state: int = 0
    stationary_initialization: bool = False
    markov_scope: str = "edge"
    profile_path: str = ""
    profile_name: str = ""
    profile_source: str = ""
    profile_symmetric: bool = True
    pairs: tuple[LatencyPairConfig, ...] = ()


@dataclass(frozen=True)
class LossConfig:
    model: str = "none"
    probability: float = 0.0
    good_to_bad: float = 0.01
    bad_to_good: float = 0.25
    loss_good: float = 0.0
    loss_bad: float = 0.8


@dataclass(frozen=True)
class ShockConfig:
    start_ms: int
    end_ms: int
    region: str
    latency_multiplier: float = 1.0
    loss_addition: float = 0.0


@dataclass(frozen=True)
class NetworkConfig:
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    loss: LossConfig = field(default_factory=LossConfig)
    shocks: tuple[ShockConfig, ...] = ()
    block_size_bytes: int = 120_000
    attestation_size_bytes: int = 512
    fanout: int = 0


@dataclass(frozen=True)
class ResourceConfig:
    enabled: bool = True
    outbound_bandwidth_mbps: float = 1000.0
    inbound_bandwidth_mbps: float = 1000.0
    processing_rate_mbps: float = 1000.0
    processing_fixed_ms: float = 0.0




@dataclass(frozen=True)
class FaultConfig:
    name: str = "outage"
    action: str = "validator_outage"
    scope: str = "global"
    targets: tuple[str, ...] = ()
    validator_ids: tuple[int, ...] = ()
    fraction: float = 0.0
    stake_fraction: float = 0.0
    start_slot: int = 0
    duration_slots: int = 1
    recovery_mode: str = "preserve_view"
    resynchronization_ms: int = 0


@dataclass(frozen=True)
class MetricsConfig:
    minimum_branch_support: float = 0.01
    orphan_settlement_slots: int = 2

@dataclass(frozen=True)
class ProtocolConfig:
    slot_duration_ms: int = 12_000
    epoch_length_slots: int = 8
    committee_fraction: float = 0.25
    attestation_delay_ms: int = 4_000
    attestation_deadline_ms: int = 8_000
    justification_threshold: float = 2 / 3
    finality_enabled: bool = True


@dataclass(frozen=True)
class ValenceConfig:
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    validators: ValidatorConfig = field(default_factory=ValidatorConfig)
    topology: TopologyConfig = field(default_factory=TopologyConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    faults: tuple[FaultConfig, ...] = ()
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    def validate(self) -> None:
        if self.validators.count < 2:
            raise ValueError("validators.count must be at least 2")
        if self.simulation.slots < 1:
            raise ValueError("simulation.slots must be positive")
        if not self.validators.regions:
            raise ValueError("validators.regions cannot be empty")
        if not self.validators.isps:
            raise ValueError("validators.isps cannot be empty")
        if self.validators.region_assignment not in {"round_robin", "weighted"}:
            raise ValueError("region_assignment must be round_robin or weighted")
        if self.validators.isp_assignment not in {"round_robin", "weighted"}:
            raise ValueError("isp_assignment must be round_robin or weighted")
        self._validate_weights(
            "region_weights", self.validators.region_weights, len(self.validators.regions),
            self.validators.region_assignment,
        )
        self._validate_weights(
            "isp_weights", self.validators.isp_weights, len(self.validators.isps),
            self.validators.isp_assignment,
        )
        if self.validators.stake_distribution not in {"equal", "lognormal", "explicit"}:
            raise ValueError("stake_distribution must be equal, lognormal, or explicit")
        if self.validators.stake_sigma <= 0:
            raise ValueError("stake_sigma must be positive")
        if self.validators.stake_distribution == "explicit":
            stakes = self.validators.explicit_stakes
            if len(stakes) != self.validators.count:
                raise ValueError("explicit_stakes length must equal validators.count")
            if any(stake <= 0 for stake in stakes):
                raise ValueError("explicit_stakes must all be positive")
        if not 0 < self.protocol.committee_fraction <= 1:
            raise ValueError("protocol.committee_fraction must be in (0, 1]")
        if self.protocol.epoch_length_slots < 1:
            raise ValueError("protocol.epoch_length_slots must be positive")
        if not 0.5 < self.protocol.justification_threshold <= 1:
            raise ValueError("justification_threshold must be in (0.5, 1]")
        if self.topology.kind not in {"ring_plus_random", "regional_clustered"}:
            raise ValueError("topology.kind must be ring_plus_random or regional_clustered")
        if self.topology.degree < 2 or self.topology.degree >= self.validators.count:
            raise ValueError("topology.degree must be >= 2 and < validators.count")
        if not 0 <= self.topology.same_region_bias <= 1:
            raise ValueError("same_region_bias must be in [0, 1]")
        if not 0 <= self.topology.same_isp_bias <= 1:
            raise ValueError("same_isp_bias must be in [0, 1]")
        if self.topology.minimum_cross_region_peers < 0:
            raise ValueError("minimum_cross_region_peers cannot be negative")
        if self.topology.minimum_cross_region_peers > self.topology.degree:
            raise ValueError("minimum_cross_region_peers cannot exceed topology.degree")
        if len(self.validators.regions) == 1 and self.topology.minimum_cross_region_peers:
            raise ValueError("cross-region peers require at least two regions")
        if self.protocol.attestation_delay_ms >= self.protocol.slot_duration_ms:
            raise ValueError("attestation_delay_ms must be less than slot_duration_ms")
        if self.protocol.attestation_deadline_ms > self.protocol.slot_duration_ms:
            raise ValueError("attestation_deadline_ms cannot exceed slot_duration_ms")
        self._validate_latency()
        if self.network.loss.model not in {"none", "bernoulli", "gilbert_elliott"}:
            raise ValueError("loss.model must be none, bernoulli, or gilbert_elliott")
        if self.resources.outbound_bandwidth_mbps <= 0:
            raise ValueError("resources.outbound_bandwidth_mbps must be positive")
        if self.resources.inbound_bandwidth_mbps <= 0:
            raise ValueError("resources.inbound_bandwidth_mbps must be positive")
        if self.resources.processing_rate_mbps <= 0:
            raise ValueError("resources.processing_rate_mbps must be positive")
        if self.resources.processing_fixed_ms < 0:
            raise ValueError("resources.processing_fixed_ms cannot be negative")
        for shock in self.network.shocks:
            if shock.end_ms <= shock.start_ms:
                raise ValueError("shock end_ms must exceed start_ms")
        if not 0 < self.metrics.minimum_branch_support <= 0.5:
            raise ValueError("metrics.minimum_branch_support must be in (0, 0.5]")
        if self.metrics.orphan_settlement_slots < 0:
            raise ValueError("metrics.orphan_settlement_slots cannot be negative")
        seen_fault_names: set[str] = set()
        for fault in self.faults:
            if fault.name in seen_fault_names:
                raise ValueError(f"duplicate fault name: {fault.name}")
            seen_fault_names.add(fault.name)
            if fault.action != "validator_outage":
                raise ValueError("fault action must currently be validator_outage")
            if fault.scope not in {
                "global", "region", "isp", "validator_ids",
                "random_fraction", "stake_fraction", "highest_stake",
            }:
                raise ValueError(f"unsupported fault scope: {fault.scope}")
            if fault.start_slot < 0 or fault.duration_slots < 1:
                raise ValueError("fault start_slot must be nonnegative and duration_slots positive")
            if fault.start_slot >= self.simulation.slots:
                raise ValueError("fault start_slot must be within the simulation")
            if fault.scope in {"region", "isp"} and not fault.targets:
                raise ValueError(f"fault {fault.name} requires targets")
            if fault.scope == "region" and any(t not in self.validators.regions for t in fault.targets):
                raise ValueError(f"fault {fault.name} uses an unknown region")
            if fault.scope == "isp" and any(t not in self.validators.isps for t in fault.targets):
                raise ValueError(f"fault {fault.name} uses an unknown ISP")
            if fault.scope == "validator_ids":
                if not fault.validator_ids:
                    raise ValueError(f"fault {fault.name} requires validator_ids")
                if any(i < 0 or i >= self.validators.count for i in fault.validator_ids):
                    raise ValueError(f"fault {fault.name} has an invalid validator ID")
            if fault.scope == "random_fraction" and not 0 < fault.fraction <= 1:
                raise ValueError("random_fraction faults require fraction in (0, 1]")
            if fault.scope in {"stake_fraction", "highest_stake"} and not 0 < fault.stake_fraction <= 1:
                raise ValueError("stake-based faults require stake_fraction in (0, 1]")
            if fault.recovery_mode not in {"preserve_view", "restart_from_finalized_checkpoint"}:
                raise ValueError("unsupported fault recovery_mode")
            if fault.resynchronization_ms < 0:
                raise ValueError("fault resynchronization_ms cannot be negative")

    @staticmethod
    def _validate_weights(name: str, values: tuple[float, ...], size: int, mode: str) -> None:
        if mode == "weighted" and not values:
            raise ValueError(f"{name} is required for weighted assignment")
        if values:
            if len(values) != size:
                raise ValueError(f"{name} length must match category count")
            if any(value < 0 for value in values) or sum(values) <= 0:
                raise ValueError(f"{name} must be nonnegative with positive total")

    @staticmethod
    def _validate_quantiles(p50: float, p95: float, p99: float, label: str) -> None:
        if not (0 < p50 < p95 < p99):
            raise ValueError(f"{label} must satisfy 0 < p50_ms < p95_ms < p99_ms")

    @classmethod
    def _validate_component(cls, component: LatencyComponentConfig, label: str) -> None:
        family = component.family
        if family not in BASE_LATENCY_FAMILIES | {"mixture"}:
            raise ValueError(f"{label}.family is unsupported: {family}")
        if component.weight <= 0:
            raise ValueError(f"{label}.weight must be positive")
        if component.calibration_mode not in {"parameters", "p50_p95"}:
            raise ValueError(f"{label}.calibration_mode must be parameters or p50_p95")
        if family in {"quantile", "quantile_piecewise"}:
            cls._validate_quantiles(
                component.p50_ms, component.p95_ms, component.p99_ms, label
            )
            if component.max_ms and component.max_ms <= component.p99_ms:
                raise ValueError(f"{label}.max_ms must exceed p99_ms")
        elif family == "empirical":
            if not component.empirical_samples_ms or any(
                value <= 0 for value in component.empirical_samples_ms
            ):
                raise ValueError(f"{label} empirical samples must be positive")
        elif family == "fixed":
            if component.fixed_ms <= 0:
                raise ValueError(f"{label}.fixed_ms must be positive")
        elif family == "truncated_normal":
            if component.stddev_ms <= 0:
                raise ValueError(f"{label}.stddev_ms must be positive")
        elif family in {"gamma", "weibull", "loglogistic", "lomax"}:
            if component.calibration_mode == "p50_p95":
                cls._validate_quantiles(
                    component.p50_ms, component.p95_ms, component.p99_ms, label
                )
            elif component.shape <= 0 or component.scale_ms <= 0:
                raise ValueError(f"{label}.shape and scale_ms must be positive")
        elif family == "generalized_pareto":
            if component.calibration_mode == "p50_p95":
                cls._validate_quantiles(
                    component.p50_ms, component.p95_ms, component.p99_ms, label
                )
            elif component.shape <= -1.0 or component.scale_ms <= 0:
                raise ValueError(
                    f"{label}.shape must exceed -1 and scale_ms must be positive"
                )
        elif family == "erlang":
            if component.erlang_stages < 1 or component.scale_ms <= 0:
                raise ValueError(f"{label}.erlang_stages and scale_ms must be positive")
        elif family == "lognormal":
            if component.calibration_mode == "p50_p95":
                cls._validate_quantiles(
                    component.p50_ms, component.p95_ms, component.p99_ms, label
                )
            elif component.mean_ms <= 0 or component.sigma <= 0:
                raise ValueError(f"{label}.mean_ms and sigma must be positive")
        elif family == "shifted_exponential":
            if component.scale_ms <= 0 or component.shift_ms < 0:
                raise ValueError(f"{label}.scale_ms must be positive and shift_ms nonnegative")
        elif family == "mixture":
            if len(component.components) < 2:
                raise ValueError(f"{label}.components must contain at least two entries")
            for index, child in enumerate(component.components):
                cls._validate_component(child, f"{label}.components[{index}]")
        if component.shift_ms < 0:
            raise ValueError(f"{label}.shift_ms cannot be negative")
        if component.max_ms and component.max_ms <= component.shift_ms:
            raise ValueError(f"{label}.max_ms must exceed shift_ms")

    def _latency_as_component(self) -> LatencyComponentConfig:
        latency = self.network.latency
        return LatencyComponentConfig(
            family=latency.distribution,
            calibration_mode=latency.calibration_mode,
            fixed_ms=latency.fixed_ms,
            shift_ms=latency.shift_ms,
            mean_ms=latency.mean_ms,
            sigma=latency.sigma,
            stddev_ms=latency.stddev_ms,
            shape=latency.shape,
            scale_ms=latency.scale_ms,
            erlang_stages=latency.erlang_stages,
            p50_ms=latency.p50_ms,
            p95_ms=latency.p95_ms,
            p99_ms=latency.p99_ms,
            max_ms=latency.max_ms,
            empirical_samples_ms=latency.empirical_samples_ms,
            components=latency.components,
        )

    def _validate_latency(self) -> None:
        latency = self.network.latency
        if latency.distribution not in TOP_LEVEL_LATENCY_FAMILIES:
            raise ValueError(
                f"latency.distribution must be one of {sorted(TOP_LEVEL_LATENCY_FAMILIES)}"
            )
        if not -0.999 <= latency.jitter_phi <= 0.999:
            raise ValueError("latency.jitter_phi must be in [-0.999, 0.999]")
        if latency.jitter_sigma_ms < 0:
            raise ValueError("latency.jitter_sigma_ms cannot be negative")

        if latency.distribution == "regional_profile":
            self._validate_quantiles(
                latency.p50_ms, latency.p95_ms, latency.p99_ms, "latency fallback"
            )
            if not latency.pairs:
                raise ValueError("regional_profile latency requires at least one pair")
        elif latency.distribution == "spliced":
            if latency.body is None or latency.tail is None:
                raise ValueError("spliced latency requires body and tail components")
            if not 0.5 < latency.splice_quantile < 1.0:
                raise ValueError("splice_quantile must be in (0.5, 1)")
            self._validate_component(latency.body, "latency.body")
            self._validate_component(latency.tail, "latency.tail")
            if latency.tail.family != "generalized_pareto":
                raise ValueError("spliced latency tail must use generalized_pareto")
            if latency.body.family in {"gamma", "erlang", "mixture", "empirical"}:
                raise ValueError(
                    "spliced body must have an analytic quantile function; "
                    "gamma, erlang, mixture, and empirical are unsupported as bodies"
                )
        elif latency.distribution == "markov_modulated":
            if len(latency.states) < 2:
                raise ValueError("markov_modulated latency requires at least two states")
            if len(latency.transition_matrix) != len(latency.states):
                raise ValueError("transition_matrix row count must match states")
            for index, state in enumerate(latency.states):
                self._validate_component(state.component, f"latency.states[{index}]")
            for row in latency.transition_matrix:
                if len(row) != len(latency.states):
                    raise ValueError("transition_matrix must be square")
                if any(value < 0 for value in row) or abs(sum(row) - 1.0) > 1e-9:
                    raise ValueError("transition_matrix rows must be nonnegative and sum to 1")
            if not latency.stationary_initialization and not 0 <= latency.initial_state < len(latency.states):
                raise ValueError("initial_state is out of range")
            if latency.markov_scope not in {"edge", "global"}:
                raise ValueError("markov_scope must be edge or global")
        else:
            self._validate_component(self._latency_as_component(), "latency")

        seen: set[tuple[str, str]] = set()
        valid_regions = set(self.validators.regions)
        for pair in latency.pairs:
            key = (pair.source_region, pair.target_region)
            if key in seen:
                raise ValueError(f"duplicate latency pair: {key}")
            seen.add(key)
            if pair.source_region not in valid_regions or pair.target_region not in valid_regions:
                raise ValueError(f"latency pair uses unknown region: {key}")
            if pair.mode not in {"quantiles", "empirical", "distribution"}:
                raise ValueError(
                    "latency pair mode must be quantiles, empirical, or distribution"
                )
            if pair.mode == "quantiles":
                self._validate_quantiles(pair.p50_ms, pair.p95_ms, pair.p99_ms, str(key))
                if pair.max_ms and pair.max_ms <= pair.p99_ms:
                    raise ValueError(f"latency pair {key} max_ms must exceed p99_ms")
            elif pair.mode == "empirical":
                if not pair.samples_ms or any(value <= 0 for value in pair.samples_ms):
                    raise ValueError(f"empirical latency pair {key} requires positive samples_ms")
            else:
                self._validate_component(_pair_component(pair), f"latency pair {key}")


def _component(raw: dict[str, Any] | None) -> LatencyComponentConfig | None:
    if raw is None:
        return None
    data = dict(raw)
    nested = tuple(_component(item) for item in data.pop("components", []))
    if any(item is None for item in nested):
        raise ValueError("latency component cannot contain null components")
    return LatencyComponentConfig(
        **{
            **data,
            "empirical_samples_ms": tuple(data.get("empirical_samples_ms", ())),
            "components": tuple(item for item in nested if item is not None),
        }
    )


def _state(raw: dict[str, Any]) -> LatencyStateConfig:
    data = dict(raw)
    component_raw = data.pop("component", None)
    if component_raw is None:
        component_raw = {key: value for key, value in data.items() if key != "name"}
        data = {"name": str(data.get("name", "state"))}
    component = _component(component_raw)
    if component is None:
        raise ValueError("latency state requires a component")
    return LatencyStateConfig(component=component, **data)


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


def _load_profile(profile_path: str, base_dir: Path) -> dict[str, Any]:
    path = Path(profile_path)
    if not path.is_absolute():
        path = base_dir / path
    with path.open("r", encoding="utf-8") as handle:
        profile = yaml.safe_load(handle) or {}
    if not isinstance(profile, dict):
        raise ValueError("Latency profile root must be a mapping")
    return profile


def _construct(data: dict[str, Any], base_dir: Path | None = None) -> ValenceConfig:
    base_dir = base_dir or Path.cwd()
    sim = SimulationConfig(**data.get("simulation", {}))
    validators_raw = data.get("validators", {})
    validators = ValidatorConfig(
        **{
            **validators_raw,
            "regions": tuple(validators_raw.get("regions", ValidatorConfig.regions)),
            "region_weights": tuple(validators_raw.get("region_weights", ())),
            "isps": tuple(validators_raw.get("isps", ValidatorConfig.isps)),
            "isp_weights": tuple(validators_raw.get("isp_weights", ())),
            "explicit_stakes": tuple(validators_raw.get("explicit_stakes", ())),
        }
    )
    topology = TopologyConfig(**data.get("topology", {}))
    network_raw = data.get("network", {})
    latency_raw = dict(network_raw.get("latency", {}))
    profile_path = str(latency_raw.get("profile_path", ""))
    if profile_path:
        profile = _load_profile(profile_path, base_dir)
        latency_raw.setdefault("profile_name", str(profile.get("name", Path(profile_path).stem)))
        latency_raw.setdefault("profile_source", str(profile.get("source", "unspecified")))
        latency_raw.setdefault("profile_symmetric", bool(profile.get("symmetric", True)))
        latency_raw["pairs"] = profile.get("pairs", latency_raw.get("pairs", []))

    pair_items = latency_raw.pop("pairs", [])
    pairs = tuple(
        LatencyPairConfig(
            **{
                **item,
                "samples_ms": tuple(item.get("samples_ms", ())),
            }
        )
        for item in pair_items
    )
    component_items = latency_raw.pop("components", [])
    components = tuple(
        component for component in (_component(item) for item in component_items)
        if component is not None
    )
    body = _component(latency_raw.pop("body", None))
    tail = _component(latency_raw.pop("tail", None))
    state_items = latency_raw.pop("states", [])
    states = tuple(_state(item) for item in state_items)
    transition_matrix = tuple(
        tuple(float(value) for value in row)
        for row in latency_raw.get("transition_matrix", ())
    )
    latency = LatencyConfig(
        **{
            **latency_raw,
            "empirical_samples_ms": tuple(latency_raw.get("empirical_samples_ms", ())),
            "components": components,
            "body": body,
            "tail": tail,
            "states": states,
            "transition_matrix": transition_matrix,
            "pairs": pairs,
        }
    )
    loss = LossConfig(**network_raw.get("loss", {}))
    shocks = tuple(ShockConfig(**item) for item in network_raw.get("shocks", []))
    network_args = {
        key: value for key, value in network_raw.items()
        if key not in {"latency", "loss", "shocks"}
    }
    network = NetworkConfig(latency=latency, loss=loss, shocks=shocks, **network_args)
    resources = ResourceConfig(**data.get("resources", {}))
    protocol = ProtocolConfig(**data.get("protocol", {}))
    faults = tuple(
        FaultConfig(
            **{
                **item,
                "targets": tuple(item.get("targets", ())),
                "validator_ids": tuple(int(value) for value in item.get("validator_ids", ())),
            }
        )
        for item in data.get("faults", [])
    )
    metrics = MetricsConfig(**data.get("metrics", {}))
    config = ValenceConfig(
        simulation=sim,
        validators=validators,
        topology=topology,
        network=network,
        resources=resources,
        protocol=protocol,
        faults=faults,
        metrics=metrics,
    )
    config.validate()
    return config


def load_config(path: str | Path) -> ValenceConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Configuration root must be a mapping")
    return _construct(raw, path.parent)
