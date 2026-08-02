import numpy as np

from valence.network import build_regional_clustered, topology_summary


def _cross_region_degree(node, topology, regions):
    return sum(regions[peer] != regions[node] for peer in topology[node])


def test_regional_topology_guarantees_degree_connectivity_and_cross_region_peers():
    regions = ["a"] * 12 + ["b"] * 10 + ["c"] * 8
    isps = ["x", "y", "z"] * 10
    topology = build_regional_clustered(
        regions,
        isps,
        degree=5,
        rng=np.random.default_rng(20),
        same_region_bias=0.85,
        minimum_cross_region_peers=1,
    )
    assert min(len(peers) for peers in topology.values()) >= 5
    assert all(_cross_region_degree(node, topology, regions) >= 1 for node in topology)
    # Undirected symmetry.
    assert all(node in topology[peer] for node, peers in topology.items() for peer in peers)


def test_higher_region_bias_increases_intra_region_edge_fraction():
    regions = ["a"] * 20 + ["b"] * 20 + ["c"] * 20
    isps = ["x", "y", "z"] * 20
    low = build_regional_clustered(
        regions,
        isps,
        degree=8,
        rng=np.random.default_rng(9),
        same_region_bias=0.20,
        minimum_cross_region_peers=1,
    )
    high = build_regional_clustered(
        regions,
        isps,
        degree=8,
        rng=np.random.default_rng(9),
        same_region_bias=0.95,
        minimum_cross_region_peers=1,
    )
    low_summary = topology_summary(low, regions, isps)
    high_summary = topology_summary(high, regions, isps)
    assert high_summary["intra_region_edge_fraction"] > low_summary["intra_region_edge_fraction"]
