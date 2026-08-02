from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from valence.model import Block, Validator


def ancestor_path(block_id: str, blocks: dict[str, Block]) -> list[str]:
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


def is_ancestor(ancestor_id: str, descendant_id: str, blocks: dict[str, Block]) -> bool:
    return ancestor_id in ancestor_path(descendant_id, blocks)


def lowest_common_ancestor(left: str, right: str, blocks: dict[str, Block]) -> str | None:
    right_ancestors = set(ancestor_path(right, blocks))
    return next((block_id for block_id in ancestor_path(left, blocks) if block_id in right_ancestors), None)


def reorganization_depth(old_head: str, new_head: str, blocks: dict[str, Block]) -> int:
    if old_head == new_head or is_ancestor(old_head, new_head, blocks):
        return 0
    common = lowest_common_ancestor(old_head, new_head, blocks)
    if common is None:
        return len(ancestor_path(old_head, blocks))
    path = ancestor_path(old_head, blocks)
    return path.index(common)


def stake_modal_head(validators: dict[int, Validator]) -> str:
    support: dict[str, float] = defaultdict(float)
    for validator in validators.values():
        support[validator.view.head_id] += validator.stake
    return min(support.items(), key=lambda item: (-item[1], item[0]))[0]


@dataclass(frozen=True)
class SupportedFork:
    heads: tuple[str, ...]
    support: dict[str, float]

    @property
    def width(self) -> int:
        return len(self.heads)


def supported_fork(
    validators: dict[int, Validator],
    blocks: dict[str, Block],
    minimum_support: float,
) -> SupportedFork | None:
    exact_support: dict[str, float] = defaultdict(float)
    for validator in validators.values():
        exact_support[validator.view.head_id] += validator.stake
    candidates = sorted(
        head for head, support in exact_support.items() if support + 1e-12 >= minimum_support
    )
    fork_heads: set[str] = set()
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if not is_ancestor(left, right, blocks) and not is_ancestor(right, left, blocks):
                fork_heads.add(left)
                fork_heads.add(right)
    if len(fork_heads) < 2:
        return None
    ordered = tuple(sorted(fork_heads))
    return SupportedFork(ordered, {head: exact_support[head] for head in ordered})


def classify_blocks(
    blocks: dict[str, Block],
    canonical_head: str,
    final_slot: int,
    settlement_slots: int,
) -> dict[str, str]:
    canonical = set(ancestor_path(canonical_head, blocks))
    settled_through = final_slot - settlement_slots
    result: dict[str, str] = {}
    for block_id, block in blocks.items():
        if block_id == "genesis":
            continue
        if block_id in canonical:
            result[block_id] = "canonical"
        elif block.slot <= settled_through:
            result[block_id] = "orphaned"
        else:
            result[block_id] = "unresolved"
    return result
