from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence


SPEC_RELEASE = "v1.6.1"
STABLE_FORK = "fulu"
DOMAIN_BEACON_PROPOSER = bytes.fromhex("00000000")
DOMAIN_BEACON_ATTESTER = bytes.fromhex("01000000")
MAX_RANDOM_BYTE = 2**8 - 1


@dataclass(frozen=True)
class EthereumPreset:
    name: str
    slot_duration_ms: int
    slots_per_epoch: int
    max_committees_per_slot: int
    target_committee_size: int
    shuffle_round_count: int
    max_effective_balance_gwei: int = 32_000_000_000
    effective_balance_increment_gwei: int = 1_000_000_000
    attestation_due_bps: int = 3333
    aggregate_due_bps: int = 6667
    proposer_score_boost: int = 40

    @property
    def attestation_due_ms(self) -> int:
        return self.slot_duration_ms * self.attestation_due_bps // 10_000

    @property
    def aggregate_due_ms(self) -> int:
        return self.slot_duration_ms * self.aggregate_due_bps // 10_000


PRESETS: Mapping[str, EthereumPreset] = {
    "minimal": EthereumPreset(
        name="minimal",
        slot_duration_ms=6_000,
        slots_per_epoch=8,
        max_committees_per_slot=4,
        target_committee_size=4,
        shuffle_round_count=10,
    ),
    "mainnet": EthereumPreset(
        name="mainnet",
        slot_duration_ms=12_000,
        slots_per_epoch=32,
        max_committees_per_slot=64,
        target_committee_size=128,
        shuffle_round_count=90,
    ),
}


def get_preset(name: str) -> EthereumPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported Ethereum preset: {name}") from exc


def hash_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def uint_to_bytes(value: int) -> bytes:
    if value < 0:
        raise ValueError("uint64 values cannot be negative")
    return int(value).to_bytes(8, "little", signed=False)


@lru_cache(maxsize=4096)
def _shuffled_permutation(index_count: int, seed: bytes, rounds: int) -> tuple[int, ...]:
    """Return the Ethereum swap-or-not permutation.

    This follows the consensus-specification algorithm while caching the full
    permutation because VALENCE repeatedly requests every committee member for
    the same epoch seed.
    """
    if index_count <= 0:
        raise ValueError("index_count must be positive")
    if len(seed) != 32:
        raise ValueError("seed must contain 32 bytes")
    if not 1 <= rounds <= 255:
        raise ValueError("rounds must be in [1, 255]")

    indices = list(range(index_count))
    for current_round in range(rounds):
        round_bytes = current_round.to_bytes(1, "little")
        pivot = int.from_bytes(hash_bytes(seed + round_bytes)[:8], "little") % index_count
        source_by_bucket: dict[int, bytes] = {}
        for position_index in range(index_count):
            current = indices[position_index]
            flip = (pivot + index_count - current) % index_count
            position = max(current, flip)
            bucket = position // 256
            source = source_by_bucket.get(bucket)
            if source is None:
                source = hash_bytes(seed + round_bytes + bucket.to_bytes(4, "little"))
                source_by_bucket[bucket] = source
            byte_value = source[(position % 256) // 8]
            bit = (byte_value >> (position % 8)) & 1
            if bit:
                indices[position_index] = flip
    return tuple(indices)


def compute_shuffled_index(index: int, index_count: int, seed: bytes, rounds: int) -> int:
    if not 0 <= index < index_count:
        raise ValueError("index must be within the shuffled range")
    return _shuffled_permutation(index_count, seed, rounds)[index]


def compute_committee(
    indices: Sequence[int],
    seed: bytes,
    index: int,
    count: int,
    rounds: int,
) -> tuple[int, ...]:
    if not indices:
        raise ValueError("indices cannot be empty")
    if not 0 <= index < count:
        raise ValueError("committee index must be in [0, count)")
    start = len(indices) * index // count
    end = len(indices) * (index + 1) // count
    return tuple(
        int(indices[compute_shuffled_index(i, len(indices), seed, rounds)])
        for i in range(start, end)
    )


def committee_count_per_slot(active_validator_count: int, preset: EthereumPreset) -> int:
    if active_validator_count <= 0:
        raise ValueError("active_validator_count must be positive")
    return max(
        1,
        min(
            preset.max_committees_per_slot,
            active_validator_count // preset.slots_per_epoch // preset.target_committee_size,
        ),
    )


def logical_effective_balances_gwei(
    stakes: Sequence[float],
    preset: EthereumPreset,
) -> tuple[int, ...]:
    """Map normalized VALENCE stake to quantized logical effective balances.

    The adapter preserves relative stake while using Ethereum's one-Gwei-unit
    effective-balance increments and 32-ETH Phase0 cap. It is intentionally a
    logical simulation adapter, not validator lifecycle or Electra credential
    processing.
    """
    if not stakes or any(float(value) <= 0 for value in stakes):
        raise ValueError("stakes must be positive")
    maximum = max(float(value) for value in stakes)
    increments = preset.max_effective_balance_gwei // preset.effective_balance_increment_gwei
    balances: list[int] = []
    for stake in stakes:
        units = max(1, int(float(stake) / maximum * increments))
        balances.append(
            min(
                preset.max_effective_balance_gwei,
                units * preset.effective_balance_increment_gwei,
            )
        )
    return tuple(balances)


def compute_proposer_index(
    indices: Sequence[int],
    effective_balances_gwei: Sequence[int],
    seed: bytes,
    preset: EthereumPreset,
) -> int:
    if not indices:
        raise ValueError("indices cannot be empty")
    if len(effective_balances_gwei) <= max(indices):
        raise ValueError("effective balances do not cover every validator index")
    i = 0
    total = len(indices)
    while True:
        candidate = int(
            indices[
                compute_shuffled_index(
                    i % total,
                    total,
                    seed,
                    preset.shuffle_round_count,
                )
            ]
        )
        random_byte = hash_bytes(seed + uint_to_bytes(i // 32))[i % 32]
        effective_balance = int(effective_balances_gwei[candidate])
        if (
            effective_balance * MAX_RANDOM_BYTE
            >= preset.max_effective_balance_gwei * random_byte
        ):
            return candidate
        i += 1


def epoch_seed(base_seed: bytes, epoch: int, domain_type: bytes) -> bytes:
    """Deterministic RANDAO surrogate for controlled simulation.

    Ethereum derives duties from a domain-separated epoch seed and RANDAO mix.
    VALENCE uses a reproducible 32-byte simulation seed in place of a modeled
    RANDAO state while preserving the domain/epoch structure.
    """
    if len(base_seed) != 32:
        raise ValueError("base_seed must contain 32 bytes")
    if len(domain_type) != 4:
        raise ValueError("domain_type must contain four bytes")
    return hash_bytes(domain_type + uint_to_bytes(epoch) + base_seed)


def base_seed_from_integer(seed: int, *, spec_release: str = SPEC_RELEASE) -> bytes:
    payload = f"VALENCE|ethereum-calibrated|{spec_release}|{int(seed)}".encode("utf-8")
    return hash_bytes(payload)
