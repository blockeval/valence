import numpy as np
import pytest

from valence.config import ProtocolConfig
from valence.model import Attestation, Block, LocalView, Message, MessageType, Validator
from valence.protocols.beacon_like import BeaconLikeProtocol


def _protocol_with_stakes(stakes: list[float]) -> tuple[BeaconLikeProtocol, Validator]:
    genesis = Block("genesis", -1, -1, None, 0)
    checkpoint = Block("checkpoint-1", 1, 0, "genesis", 100)
    validators: dict[int, Validator] = {}
    for validator_id, stake in enumerate(stakes):
        view = LocalView(
            known_blocks={"genesis": genesis, "checkpoint-1": checkpoint},
            children={"genesis": {"checkpoint-1"}, "checkpoint-1": set()},
            head_id="checkpoint-1",
        )
        validators[validator_id] = Validator(
            validator_id=validator_id,
            stake=stake,
            region="r",
            isp="i",
            peers=tuple(i for i in range(len(stakes)) if i != validator_id),
            view=view,
        )
    protocol = BeaconLikeProtocol(
        ProtocolConfig(epoch_length_slots=2, committee_fraction=1.0),
        validators,
        np.random.default_rng(1),
        np.random.default_rng(2),
        total_slots=1,
    )
    return protocol, validators[0]


def _add_vote(protocol: BeaconLikeProtocol, observer: Validator, validator_id: int) -> None:
    stake = protocol.stake_by_validator[validator_id]
    attestation = Attestation(
        attestation_id=f"vote-{validator_id}",
        slot=2,
        validator_id=validator_id,
        block_id="checkpoint-1",
        created_at_ms=1000 + validator_id,
        stake=stake,
        source_checkpoint_id="genesis",
        source_epoch=0,
        target_checkpoint_id="checkpoint-1",
        target_epoch=1,
    )
    protocol.process_message(
        observer,
        Message(
            message_id=f"message-{validator_id}",
            message_type=MessageType.ATTESTATION,
            creator_id=validator_id,
            slot=2,
            created_at_ms=attestation.created_at_ms,
            size_bytes=512,
            body=attestation,
        ),
    )


def test_finality_does_not_justify_below_two_thirds_stake():
    protocol, observer = _protocol_with_stakes([0.4, 0.3, 0.2, 0.1])
    _add_vote(protocol, observer, 0)
    _add_vote(protocol, observer, 2)  # 0.60 stake
    transition = protocol.update_finality(observer, target_epoch=1)
    assert transition is not None
    assert transition.justified is False
    assert transition.supporting_stake == pytest.approx(0.6)
    assert observer.view.justified_epoch == 0
    assert observer.view.finalized_epoch == 0


def test_stake_weighted_supermajority_can_be_fewer_validators():
    protocol, observer = _protocol_with_stakes([0.4, 0.3, 0.2, 0.1])
    _add_vote(protocol, observer, 0)
    _add_vote(protocol, observer, 1)  # Two of four validators, but 0.70 stake.
    transition = protocol.update_finality(observer, target_epoch=1)
    assert transition is not None
    assert transition.justified is True
    assert transition.supporting_stake == pytest.approx(0.7)
    assert observer.view.justified_epoch == 1
    assert observer.view.justified_checkpoint == "checkpoint-1"
    assert transition.finalized_epoch == 0
    assert transition.finalized_checkpoint_id == "genesis"


def test_finality_is_monotonic():
    protocol, observer = _protocol_with_stakes([0.4, 0.3, 0.2, 0.1])
    _add_vote(protocol, observer, 0)
    _add_vote(protocol, observer, 1)
    first = protocol.update_finality(observer, target_epoch=1)
    second = protocol.update_finality(observer, target_epoch=1)
    assert first is not None and first.justified
    assert second is None
    assert observer.view.justified_epoch == 1
    assert observer.view.finalized_epoch == 0
