"""Unit-тести типізованого AM1 generator та architecture interventions."""

from __future__ import annotations

import networkx as nx
import pytest

from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import (
    ARCHITECTURES,
    INTERVENTION_BUDGET,
    MATERIAL_RELATIONS,
    ROLE_COUNTS,
    apply_architecture,
    generate_am_network,
)


@pytest.mark.parametrize("N", [50, 80])
def test_role_counts_and_end_to_end_routes(N: int) -> None:
    network = generate_am_network(N=N, seed=42)

    assert network.N == N
    for role, count in ROLE_COUNTS[N].items():
        assert len(network.nodes_by_role(role)) == count
    assert compute_max_flow(network) > 0.0
    for demand in network.consumers:
        assert any(
            nx.has_path(network.graph, supplier, demand)
            for supplier in network.suppliers
        )


@pytest.mark.parametrize("N", [50, 80])
def test_material_edges_only_join_adjacent_stages(N: int) -> None:
    network = generate_am_network(N=N, seed=7)

    for source, target in network.graph.edges:
        roles = (
            network.graph.nodes[source]["role"],
            network.graph.nodes[target]["role"],
        )
        assert roles in MATERIAL_RELATIONS


def test_generator_is_seed_deterministic() -> None:
    left = generate_am_network(N=50, seed=123)
    right = generate_am_network(N=50, seed=123)

    assert sorted(left.graph.edges) == sorted(right.graph.edges)
    assert left._base_capacities == right._base_capacities
    assert left.digital_dependencies == right.digital_dependencies
    assert left.intervention_catalog == right.intervention_catalog


@pytest.mark.parametrize("N", [50, 80])
@pytest.mark.parametrize("architecture", sorted(ARCHITECTURES))
def test_architecture_budget_and_base_isolation(N: int, architecture: str) -> None:
    base = generate_am_network(N=N, seed=19)
    base_edges = set(base.graph.edges)
    base_dependencies = {
        hub: set(services) for hub, services in base.digital_dependencies.items()
    }

    variant = apply_architecture(base, architecture)

    expected = 0 if architecture == "A0_baseline" else INTERVENTION_BUDGET[N]
    assert len(variant.applied_relations) == expected
    assert set(base.graph.edges) == base_edges
    assert base.digital_dependencies == base_dependencies


def test_balanced_architecture_spreads_budget_equally() -> None:
    base = generate_am_network(N=50, seed=81)
    variant = apply_architecture(base, "A5_balanced")
    categories = [relation.category for relation in variant.applied_relations]

    assert categories.count("feedstock") == 2
    assert categories.count("cross_qualification") == 2
    assert categories.count("downstream") == 2
    assert categories.count("digital") == 2


def test_downstream_architecture_covers_both_downstream_stages() -> None:
    base = generate_am_network(N=50, seed=82)
    variant = apply_architecture(base, "A3_downstream")
    role_pairs = {
        (
            variant.graph.nodes[relation.source]["role"],
            variant.graph.nodes[relation.target]["role"],
        )
        for relation in variant.applied_relations
    }

    assert ("am_hub", "post_processing") in role_pairs
    assert ("post_processing", "quality_assurance") in role_pairs


def test_copy_is_independent() -> None:
    base = generate_am_network(N=50, seed=3)
    copied = base.copy()
    hub = copied.nodes_by_role("am_hub")[0]

    copied.fail_physical(hub)

    assert hub in copied.physical_failed_nodes
    assert hub not in base.physical_failed_nodes
    assert hub not in base.failed_nodes
