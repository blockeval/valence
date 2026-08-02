from __future__ import annotations

from collections import defaultdict

import numpy as np


def build_ring_plus_random(
    count: int,
    degree: int,
    rng: np.random.Generator,
) -> dict[int, tuple[int, ...]]:
    """Build a connected undirected overlay with a ring and random extra edges."""
    if degree >= count:
        raise ValueError("degree must be less than count")
    peers: dict[int, set[int]] = {i: set() for i in range(count)}
    for i in range(count):
        j = (i + 1) % count
        peers[i].add(j)
        peers[j].add(i)
    _fill_minimum_degree(peers, degree, rng)
    return {i: tuple(sorted(values)) for i, values in peers.items()}


def build_regional_clustered(
    regions: list[str],
    isps: list[str],
    degree: int,
    rng: np.random.Generator,
    *,
    same_region_bias: float = 0.8,
    same_isp_bias: float = 0.0,
    minimum_cross_region_peers: int = 1,
) -> dict[int, tuple[int, ...]]:
    """Build a connected overlay with controllable geographic clustering.

    The target ``degree`` is a minimum, not a hard maximum, because undirected
    edges and cross-region guarantees can increase some node degrees.
    """
    count = len(regions)
    if len(isps) != count:
        raise ValueError("regions and isps must have equal length")
    if degree >= count:
        raise ValueError("degree must be less than count")

    peers: dict[int, set[int]] = {i: set() for i in range(count)}
    by_region: dict[str, list[int]] = defaultdict(list)
    for node, region in enumerate(regions):
        by_region[region].append(node)

    # Local rings provide resilient within-region connectivity.
    for nodes in by_region.values():
        if len(nodes) == 2:
            _add_edge(peers, nodes[0], nodes[1])
        elif len(nodes) > 2:
            for index, node in enumerate(nodes):
                _add_edge(peers, node, nodes[(index + 1) % len(nodes)])

    # A ring of region representatives guarantees global connectivity.
    representatives = [nodes[0] for _, nodes in sorted(by_region.items())]
    if len(representatives) > 1:
        for index, node in enumerate(representatives):
            _add_edge(peers, node, representatives[(index + 1) % len(representatives)])

    # Give every node the requested number of cross-region peers where possible.
    if len(by_region) > 1:
        for node in range(count):
            while _cross_region_degree(node, peers, regions) < minimum_cross_region_peers:
                candidates = [
                    other for other in range(count)
                    if other != node
                    and regions[other] != regions[node]
                    and other not in peers[node]
                ]
                if not candidates:
                    break
                weights = np.asarray(
                    [1.0 + same_isp_bias * float(isps[other] == isps[node]) for other in candidates],
                    dtype=float,
                )
                weights /= weights.sum()
                other = int(rng.choice(candidates, p=weights))
                _add_edge(peers, node, other)

    attempts = 0
    max_attempts = count * count * 50
    while min(len(values) for values in peers.values()) < degree and attempts < max_attempts:
        candidates_needing_edges = [node for node in range(count) if len(peers[node]) < degree]
        node = int(rng.choice(candidates_needing_edges))
        candidates = [
            other for other in range(count)
            if other != node and other not in peers[node]
        ]
        if not candidates:
            attempts += 1
            continue
        weights = []
        for other in candidates:
            same_region = regions[other] == regions[node]
            region_weight = same_region_bias if same_region else (1.0 - same_region_bias)
            # Keep both classes selectable even at bias endpoints.
            region_weight = max(region_weight, 1e-6)
            isp_multiplier = 1.0 + same_isp_bias * float(isps[other] == isps[node])
            weights.append(region_weight * isp_multiplier)
        probabilities = np.asarray(weights, dtype=float)
        probabilities /= probabilities.sum()
        other = int(rng.choice(candidates, p=probabilities))
        _add_edge(peers, node, other)
        attempts += 1

    if min(len(values) for values in peers.values()) < degree:
        raise RuntimeError("Could not construct requested regional topology")
    return {i: tuple(sorted(values)) for i, values in peers.items()}


def topology_summary(
    topology: dict[int, tuple[int, ...]],
    regions: list[str],
    isps: list[str],
) -> dict[str, float | int]:
    edges = {
        tuple(sorted((source, target)))
        for source, targets in topology.items()
        for target in targets
        if source != target
    }
    intra_region = sum(regions[a] == regions[b] for a, b in edges)
    intra_isp = sum(isps[a] == isps[b] for a, b in edges)
    edge_count = len(edges)
    degrees = [len(topology[node]) for node in sorted(topology)]
    return {
        "overlay_edge_count": edge_count,
        "mean_overlay_degree": round(sum(degrees) / len(degrees), 12),
        "minimum_overlay_degree": min(degrees),
        "maximum_overlay_degree": max(degrees),
        "intra_region_edge_fraction": round(intra_region / edge_count, 12) if edge_count else 0.0,
        "cross_region_edge_fraction": round(1 - intra_region / edge_count, 12) if edge_count else 0.0,
        "intra_isp_edge_fraction": round(intra_isp / edge_count, 12) if edge_count else 0.0,
    }


def _add_edge(peers: dict[int, set[int]], first: int, second: int) -> None:
    if first == second:
        return
    peers[first].add(second)
    peers[second].add(first)


def _cross_region_degree(node: int, peers: dict[int, set[int]], regions: list[str]) -> int:
    return sum(regions[other] != regions[node] for other in peers[node])


def _fill_minimum_degree(
    peers: dict[int, set[int]],
    degree: int,
    rng: np.random.Generator,
) -> None:
    count = len(peers)
    attempts = 0
    max_attempts = count * count * 20
    while min(len(values) for values in peers.values()) < degree and attempts < max_attempts:
        candidates = [node for node in range(count) if len(peers[node]) < degree]
        node = int(rng.choice(candidates))
        possible = [
            other for other in range(count)
            if other != node and other not in peers[node] and len(peers[other]) < degree
        ]
        if not possible:
            possible = [other for other in range(count) if other != node and other not in peers[node]]
        if possible:
            _add_edge(peers, node, int(rng.choice(possible)))
        attempts += 1
    if min(len(values) for values in peers.values()) < degree:
        raise RuntimeError("Could not construct requested topology")
