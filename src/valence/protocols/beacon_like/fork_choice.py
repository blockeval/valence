from __future__ import annotations

from valence.model import Block, LocalView


def ancestor_path(block_id: str, blocks: dict[str, Block]) -> list[str]:
    """Return block and known ancestors through genesis."""
    path: list[str] = []
    current = block_id
    visited: set[str] = set()
    while current not in visited:
        visited.add(current)
        path.append(current)
        if current == "genesis":
            break
        block = blocks.get(current)
        if block is None or block.parent_id is None:
            break
        current = block.parent_id
    return path


def adjust_vote(view: LocalView, block_id: str, delta: float) -> None:
    if block_id not in view.known_blocks:
        return
    for ancestor in ancestor_path(block_id, view.known_blocks):
        view.subtree_vote_weight[ancestor] = view.subtree_vote_weight.get(ancestor, 0.0) + delta


def rebuild_vote_weights(view: LocalView, stake_by_validator: dict[int, float]) -> None:
    view.subtree_vote_weight = {block_id: 0.0 for block_id in view.known_blocks}
    for validator_id, attestation in view.latest_attestations.items():
        adjust_vote(view, attestation.block_id, stake_by_validator[validator_id])


def lmd_ghost_head(view: LocalView) -> str:
    """Traverse the locally known block tree using cached subtree vote weights."""
    current = view.justified_checkpoint
    while view.children.get(current):
        candidates = []
        for child in view.children[current]:
            block = view.known_blocks[child]
            candidates.append(
                (view.subtree_vote_weight.get(child, 0.0), block.slot, child)
            )
        best_weight = max(item[0] for item in candidates)
        best_slot = max(item[1] for item in candidates if item[0] == best_weight)
        current = min(
            item[2]
            for item in candidates
            if item[0] == best_weight and item[1] == best_slot
        )
    return current
