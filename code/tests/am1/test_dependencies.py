"""Unit-тести digital enabling dependencies і failover AM1."""

from src.am1.network import apply_architecture, generate_am_network


def test_primary_outage_blocks_unprotected_hubs() -> None:
    network = generate_am_network(N=50, seed=11)
    primary = network.am_metadata["primary_digital_service"]

    network.fail_digital_service(primary)

    assert network.dependency_blocked_nodes == set(network.nodes_by_role("am_hub"))
    assert network.repairable_nodes() == {primary}


def test_digital_architecture_protects_exact_budget_hubs() -> None:
    base = generate_am_network(N=50, seed=11)
    network = apply_architecture(base, "A4_digital")
    primary = network.am_metadata["primary_digital_service"]
    budget = network.am_metadata["intervention_budget"]

    network.fail_digital_service(primary)

    protected = set(network.nodes_by_role("am_hub")) - network.dependency_blocked_nodes
    assert len(protected) == budget


def test_service_repair_releases_dependency_block() -> None:
    network = generate_am_network(N=50, seed=22)
    primary = network.am_metadata["primary_digital_service"]

    network.fail_digital_service(primary)
    assert network.dependency_blocked_nodes
    network.repair_digital_service(primary)

    assert network.dependency_blocked_nodes == set()
    assert primary not in network.failed_nodes


def test_physical_failure_survives_digital_service_repair() -> None:
    network = generate_am_network(N=50, seed=22)
    primary = network.am_metadata["primary_digital_service"]
    hub = network.nodes_by_role("am_hub")[0]

    network.fail_physical(hub)
    network.fail_digital_service(primary)
    network.repair_digital_service(primary)

    assert hub in network.physical_failed_nodes
    assert hub in network.failed_nodes
