"""Стабільний AM1-adapter до незмінного flow interface попередніх статей.

Основний шлях викликає канонічний ``src.network.flow.compute_max_flow``.
Для рідкісної помилки NetworkX preflow-push на графах із floating-point
capacities використовується математично еквівалентний Edmonds–Karp fallback.
Базовий flow-модуль та результати статей 1–4 не змінюються.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx

from src.network.flow import build_extended_graph, compute_max_flow as _base_max_flow

if TYPE_CHECKING:
    from src.network.base import Network


_SUPER_SOURCE = "__SUPER_SOURCE__"
_SUPER_SINK = "__SUPER_SINK__"


def compute_am_max_flow(network: "Network") -> float:
    """Обчислює max flow через базовий interface з вузьким fallback."""
    try:
        return _base_max_flow(network)
    except ValueError as exc:
        if "min() iterable argument is empty" not in str(exc):
            raise

    extended = build_extended_graph(network)
    try:
        value, _ = nx.maximum_flow(
            extended,
            _SUPER_SOURCE,
            _SUPER_SINK,
            capacity="capacity",
            flow_func=nx.algorithms.flow.edmonds_karp,
        )
        return float(value)
    except nx.NetworkXError:
        return 0.0
