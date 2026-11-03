"""Unit-тести AM1-specific disruption mechanisms."""

import math

from src.am1.disruptions import (
    apply_primary_digital_outage,
    apply_printer_random_fixed_budget,
    apply_regional_cluster,
    apply_targeted_role_failure,
    select_targeted_role_node,
)
from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import apply_architecture, generate_am_network


def test_printer_failure_uses_fixed_budget_and_seed() -> None:
    left = generate_am_network(N=50, seed=5)
    right = generate_am_network(N=50, seed=5)

    selected_left = apply_printer_random_fixed_budget(left, seed=901, fraction=0.20)
    selected_right = apply_printer_random_fixed_budget(right, seed=901, fraction=0.20)

    expected = math.ceil(0.20 * len(left.nodes_by_role("am_hub")))
    assert selected_left == selected_right
    assert len(selected_left) == expected
    assert set(selected_left) == left.physical_failed_nodes


def test_targeted_failures_select_requested_roles() -> None:
    feedstock = generate_am_network(N=50, seed=6)
    postprocess = generate_am_network(N=50, seed=6)

    selected_supplier = apply_targeted_role_failure(feedstock, "feedstock_supplier")
    selected_post = apply_targeted_role_failure(postprocess, "post_processing")

    assert feedstock.graph.nodes[selected_supplier]["role"] == "feedstock_supplier"
    assert postprocess.graph.nodes[selected_post]["role"] == "post_processing"
    assert selected_supplier in feedstock.physical_failed_nodes
    assert selected_post in postprocess.physical_failed_nodes


def test_targeted_pair_can_reuse_baseline_target_without_reselection() -> None:
    base = generate_am_network(N=50, seed=66)
    variant = apply_architecture(base, "A1_feedstock")
    shared_target = select_targeted_role_node(base, "feedstock_supplier")

    selected_base = apply_targeted_role_failure(
        base, "feedstock_supplier", selected=shared_target
    )
    selected_variant = apply_targeted_role_failure(
        variant, "feedstock_supplier", selected=shared_target
    )

    assert selected_base == selected_variant == shared_target


def test_digital_backup_reduces_blocked_hubs_and_preserves_more_flow() -> None:
    base = generate_am_network(N=50, seed=9)
    protected = apply_architecture(base, "A4_digital")
    baseline = apply_architecture(base, "A0_baseline")

    apply_primary_digital_outage(baseline)
    apply_primary_digital_outage(protected)

    assert len(protected.dependency_blocked_nodes) < len(baseline.dependency_blocked_nodes)
    assert compute_max_flow(protected) >= compute_max_flow(baseline)


def test_regional_cluster_is_seed_deterministic_and_excludes_demand() -> None:
    left = generate_am_network(N=50, seed=10)
    right = generate_am_network(N=50, seed=10)

    region_left, selected_left = apply_regional_cluster(left, seed=902)
    region_right, selected_right = apply_regional_cluster(right, seed=902)

    assert region_left == region_right
    assert selected_left == selected_right
    assert selected_left
    assert all(left.graph.nodes[node]["role"] != "demand" for node in selected_left)
    assert set(selected_left) == left.physical_failed_nodes
