from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from valence.model import Attestation, Block, LocalView
from .fork_choice import ancestor_path


@dataclass(frozen=True)
class FinalityTransition:
    target_epoch: int
    target_checkpoint_id: str
    supporting_stake: float
    justified: bool
    finalized_epoch: int | None = None
    finalized_checkpoint_id: str | None = None


def checkpoint_for_epoch(
    view: LocalView,
    epoch: int,
    epoch_length_slots: int,
) -> str:
    """Return the locally known checkpoint available at the start of an epoch.

    Epoch 0 is rooted at genesis. For epoch e > 0, the checkpoint is the
    highest ancestor of the local head with slot <= e * epoch_length_slots - 1.
    This intentionally models an epoch-boundary checkpoint without claiming
    exact Ethereum compatibility.
    """
    if epoch <= 0:
        return "genesis"
    boundary_slot = epoch * epoch_length_slots - 1
    candidates: list[Block] = []
    for block_id in ancestor_path(view.head_id, view.known_blocks):
        block = view.known_blocks.get(block_id)
        if block is not None and block.slot <= boundary_slot:
            candidates.append(block)
    if not candidates:
        return "genesis"
    best = max(candidates, key=lambda block: (block.slot, block.block_id))
    return best.block_id


def record_finality_vote(view: LocalView, attestation: Attestation) -> None:
    """Keep one latest FFG-style vote per validator and target epoch."""
    key = (attestation.target_epoch, attestation.validator_id)
    previous = view.finality_votes.get(key)
    if previous is None or (attestation.slot, attestation.created_at_ms) > (
        previous.slot,
        previous.created_at_ms,
    ):
        view.finality_votes[key] = attestation


def update_finality(
    view: LocalView,
    target_epoch: int,
    stake_by_validator: dict[int, float],
    threshold: float,
) -> FinalityTransition | None:
    """Apply a simplified, local Casper-FFG-style checkpoint transition.

    Votes are grouped by source and target checkpoint. A target is justified
    only when the source equals the observer's current justified checkpoint and
    the unique supporting validator stake reaches the configured threshold.
    A directly linked source checkpoint is finalized when its child target is
    justified. Epochs and finality can only move forward.
    """
    if target_epoch <= view.justified_epoch:
        return None

    support: dict[tuple[str, int, str, int], float] = defaultdict(float)
    for (vote_epoch, validator_id), vote in view.finality_votes.items():
        if vote_epoch != target_epoch:
            continue
        key = (
            vote.source_checkpoint_id,
            vote.source_epoch,
            vote.target_checkpoint_id,
            vote.target_epoch,
        )
        support[key] += stake_by_validator[validator_id]

    eligible: list[tuple[float, int, str, tuple[str, int, str, int]]] = []
    for key, weight in support.items():
        source_id, source_epoch, target_id, vote_target_epoch = key
        if source_id != view.justified_checkpoint or source_epoch != view.justified_epoch:
            continue
        if vote_target_epoch != target_epoch:
            continue
        target_block = view.known_blocks.get(target_id)
        if target_block is None:
            continue
        target_slot = target_block.slot
        eligible.append((weight, target_slot, target_id, key))

    if not eligible:
        return None

    weight, _slot, target_id, key = max(
        eligible,
        key=lambda item: (item[0], item[1], item[2]),
    )
    source_id, source_epoch, _target_id, _vote_target_epoch = key
    if weight + 1e-12 < threshold:
        return FinalityTransition(target_epoch, target_id, weight, justified=False)

    finalized_epoch: int | None = None
    finalized_id: str | None = None
    if target_epoch == source_epoch + 1 and source_epoch >= view.finalized_epoch:
        finalized_epoch = source_epoch
        finalized_id = source_id
        view.finalized_epoch = source_epoch
        view.finalized_checkpoint = source_id

    view.justified_epoch = target_epoch
    view.justified_checkpoint = target_id
    return FinalityTransition(
        target_epoch=target_epoch,
        target_checkpoint_id=target_id,
        supporting_stake=weight,
        justified=True,
        finalized_epoch=finalized_epoch,
        finalized_checkpoint_id=finalized_id,
    )
