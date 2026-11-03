"""Політики відновлення для AM1.

Основна політика ``flow_greedy_am`` порівнює лише реально пошкоджені
фізичні вузли та цифрові сервіси. Каскадно заблоковані AM hubs не є окремими
repairable elements: вони повертаються до роботи після відновлення хоча б
одного призначеного цифрового сервісу.
"""

from __future__ import annotations

import numpy as np

from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import AMNetwork


class FlowGreedyAMRecovery:
    """Детермінована AM-адаптація flow-greedy recovery."""

    name = "flow_greedy_am"

    def select_element_to_repair(
        self,
        network: AMNetwork,
        t: int,
    ) -> str | None:
        """Обирає repairable element з найбільшим поточним приростом потоку.

        ``t`` входить до interface для сумісності з іншими recovery policies,
        але стаціонарна AM1-політика не змінює правило вибору з часом.
        """
        del t
        candidates = sorted(network.repairable_nodes())
        if not candidates:
            return None

        current_flow = compute_max_flow(network)
        scored: list[tuple[float, str]] = []
        for element in candidates:
            restored = network.copy()
            _repair_element(restored, element)
            gain = compute_max_flow(restored) - current_flow
            scored.append((float(gain), element))

        best_gain = max(gain for gain, _ in scored)
        return min(
            element
            for gain, element in scored
            if np.isclose(gain, best_gain, rtol=1e-12, atol=1e-12)
        )

    def repair(self, network: AMNetwork, element: str) -> None:
        """Відновлює обраний фізичний вузол або цифровий сервіс."""
        if element not in network.repairable_nodes():
            raise ValueError(f"AM1 element {element!r} не потребує відновлення.")
        _repair_element(network, element)


class RandomAMRecovery:
    """Secondary calibration benchmark; не є фактором основного AM1-плану."""

    name = "random_am"

    def select_element_to_repair(
        self,
        network: AMNetwork,
        t: int,
        rng: np.random.Generator,
    ) -> str | None:
        del t
        candidates = sorted(network.repairable_nodes())
        if not candidates:
            return None
        return str(rng.choice(candidates))

    def repair(self, network: AMNetwork, element: str) -> None:
        if element not in network.repairable_nodes():
            raise ValueError(f"AM1 element {element!r} не потребує відновлення.")
        _repair_element(network, element)


def _repair_element(network: AMNetwork, element: str) -> None:
    """Маршрутизує repair без зміни базового ``Network`` API."""
    if element in network.failed_digital_services:
        network.repair_digital_service(element)
    elif element in network.physical_failed_nodes:
        network.repair_physical(element)
    else:
        raise ValueError(f"AM1 element {element!r} не є фізично пошкодженим.")


def get_am_recovery(name: str) -> FlowGreedyAMRecovery | RandomAMRecovery:
    """Створює AM1 recovery policy за назвою з конфігурації."""
    if name == FlowGreedyAMRecovery.name:
        return FlowGreedyAMRecovery()
    if name == RandomAMRecovery.name:
        return RandomAMRecovery()
    raise ValueError(
        f"Невідома AM1 recovery policy {name!r}; "
        "дозволені flow_greedy_am, random_am."
    )
