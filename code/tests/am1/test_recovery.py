"""Тести AM1 recovery без втручання в recovery-код попередніх статей."""

from src.am1.disruptions import (
    apply_primary_digital_outage,
    apply_printer_random_fixed_budget,
)
from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import apply_architecture, generate_am_network
from src.am1.recovery import FlowGreedyAMRecovery


def test_digital_service_is_repaired_instead_of_blocked_hubs() -> None:
    network = apply_architecture(generate_am_network(50, 42), "A4_digital")
    service = apply_primary_digital_outage(network)
    blocked_before = set(network.dependency_blocked_nodes)

    recovery = FlowGreedyAMRecovery()
    selected = recovery.select_element_to_repair(network, t=1)

    assert blocked_before
    assert selected == service
    assert selected not in blocked_before
    recovery.repair(network, selected)
    assert not network.failed_digital_services
    assert not network.dependency_blocked_nodes


def test_flow_greedy_am_is_deterministic_for_same_state() -> None:
    first = generate_am_network(50, 17)
    second = generate_am_network(50, 17)
    apply_printer_random_fixed_budget(first, seed=19)
    apply_printer_random_fixed_budget(second, seed=19)

    recovery = FlowGreedyAMRecovery()
    assert recovery.select_element_to_repair(first, 1) == recovery.select_element_to_repair(second, 1)


def test_each_repair_removes_one_real_failure_and_never_lowers_flow() -> None:
    network = generate_am_network(50, 21)
    apply_printer_random_fixed_budget(network, seed=22)
    recovery = FlowGreedyAMRecovery()
    previous_count = len(network.repairable_nodes())
    previous_flow = compute_max_flow(network)

    selected = recovery.select_element_to_repair(network, 1)
    assert selected is not None
    recovery.repair(network, selected)

    assert len(network.repairable_nodes()) == previous_count - 1
    assert compute_max_flow(network) >= previous_flow
