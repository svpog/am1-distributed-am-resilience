"""AM-специфічні порушення для Stage A протоколу AM1."""

from __future__ import annotations

import math

import numpy as np

from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import AMNetwork


def apply_printer_random_fixed_budget(
    network: AMNetwork,
    seed: int,
    fraction: float = 0.20,
) -> list[str]:
    """Виводить з ладу fixed-budget частку AM hubs."""
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction має належати інтервалу (0, 1].")
    hubs = network.nodes_by_role("am_hub")
    k = max(1, math.ceil(fraction * len(hubs)))
    rng = np.random.default_rng(seed)
    selected = sorted(str(node) for node in rng.choice(hubs, size=k, replace=False))
    for node in selected:
        network.fail_physical(node)
    network.disruption_metadata.update(
        {"scenario": "D1_printer_random", "seed": seed, "selected": selected}
    )
    return selected


def select_targeted_role_node(network: AMNetwork, role: str) -> str:
    """Обирає role-вузол із найбільшим падінням max flow без мутації мережі."""
    if role not in {"feedstock_supplier", "post_processing"}:
        raise ValueError("Targeted AM1 role має бути feedstock_supplier або post_processing.")
    baseline = compute_max_flow(network)
    scored: list[tuple[float, str]] = []
    for node in network.nodes_by_role(role):
        candidate = network.copy()
        candidate.fail_physical(node)
        drop = baseline - compute_max_flow(candidate)
        scored.append((drop, node))
    if not scored:
        raise RuntimeError(f"Немає candidate nodes для role={role!r}.")
    max_drop = max(score for score, _ in scored)
    return min(node for score, node in scored if np.isclose(score, max_drop))


def apply_targeted_role_failure(
    network: AMNetwork,
    role: str,
    selected: str | None = None,
) -> str:
    """Пошкоджує спільну paired target або обирає її на переданій мережі."""
    if selected is None:
        selected = select_targeted_role_node(network, role)
    if selected not in network.nodes_by_role(role):
        raise ValueError(f"Target {selected!r} не належить до role={role!r}.")
    baseline = compute_max_flow(network)
    candidate = network.copy()
    candidate.fail_physical(selected)
    max_drop = baseline - compute_max_flow(candidate)
    network.fail_physical(selected)
    scenario = (
        "D2_feedstock_targeted"
        if role == "feedstock_supplier"
        else "D3_postprocess_targeted"
    )
    network.disruption_metadata.update(
        {"scenario": scenario, "selected": [selected], "flow_drop": max_drop}
    )
    return selected


def apply_primary_digital_outage(network: AMNetwork) -> str:
    """Вимикає primary service з найбільшою кількістю AM dependants."""
    services = network.nodes_by_role("digital_service")
    dependency_count = {
        service: sum(
            service in assigned
            for assigned in network.digital_dependencies.values()
        )
        for service in services
    }
    max_count = max(dependency_count.values())
    selected = min(
        service for service, count in dependency_count.items() if count == max_count
    )
    network.fail_digital_service(selected)
    network.disruption_metadata.update(
        {
            "scenario": "D4_digital_outage",
            "selected": [selected],
            "blocked_hubs": sorted(network.dependency_blocked_nodes),
        }
    )
    return selected


def apply_regional_cluster(network: AMNetwork, seed: int) -> tuple[str, list[str]]:
    """Пошкоджує всі фізичні production nodes однієї seed-визначеної region."""
    eligible_roles = {
        "feedstock_supplier",
        "preprocessing",
        "am_hub",
        "post_processing",
        "quality_assurance",
    }
    regions = sorted(
        {
            data["region"]
            for _, data in network.graph.nodes(data=True)
            if data.get("role") in eligible_roles
        }
    )
    rng = np.random.default_rng(seed)
    region = str(rng.choice(regions))
    selected = sorted(
        node for node, data in network.graph.nodes(data=True)
        if data.get("region") == region and data.get("role") in eligible_roles
    )
    for node in selected:
        network.fail_physical(node)
    network.disruption_metadata.update(
        {
            "scenario": "D5_regional_cluster",
            "seed": seed,
            "region": region,
            "selected": selected,
        }
    )
    return region, selected
