"""Типізований генератор мережі розподіленого адитивного виробництва AM1.

Модуль є новим ізольованим шаром над незмінною базовою ``Network``. Він не
входить до генераторів статей 1–4 і не змінює їхню поведінку.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np

from src.am1.dependencies import add_digital_backup, dependency_blocked_hubs
from src.network.base import Network


ROLE_COUNTS: dict[int, dict[str, int]] = {
    50: {
        "feedstock_supplier": 4,
        "preprocessing": 6,
        "am_hub": 20,
        "post_processing": 6,
        "quality_assurance": 4,
        "demand": 8,
        "digital_service": 2,
    },
    80: {
        "feedstock_supplier": 6,
        "preprocessing": 8,
        "am_hub": 32,
        "post_processing": 10,
        "quality_assurance": 6,
        "demand": 16,
        "digital_service": 2,
    },
}

ARCHITECTURES = {
    "A0_baseline",
    "A1_feedstock",
    "A2_cross_qualification",
    "A3_downstream",
    "A4_digital",
    "A5_balanced",
}

INTERVENTION_BUDGET = {50: 8, 80: 12}

STAGE_ORDER = (
    "feedstock_supplier",
    "preprocessing",
    "am_hub",
    "post_processing",
    "quality_assurance",
    "demand",
)

MATERIAL_RELATIONS = {
    ("feedstock_supplier", "preprocessing"),
    ("preprocessing", "am_hub"),
    ("am_hub", "post_processing"),
    ("post_processing", "quality_assurance"),
    ("quality_assurance", "demand"),
}

CAPACITY_RANGES: dict[tuple[str, str], tuple[float, float]] = {
    ("feedstock_supplier", "preprocessing"): (70.0, 110.0),
    ("preprocessing", "am_hub"): (24.0, 42.0),
    ("am_hub", "post_processing"): (18.0, 34.0),
    ("post_processing", "quality_assurance"): (50.0, 90.0),
    ("quality_assurance", "demand"): (25.0, 45.0),
}


@dataclass(frozen=True)
class MaterialRelation:
    """Кандидатна кваліфікована material-flow relation."""

    source: str
    target: str
    capacity: float
    category: str


@dataclass(frozen=True)
class DigitalRelation:
    """Кандидатна backup-service enabling relation."""

    service: str
    hub: str
    category: str = "digital"


class AMNetwork(Network):
    """Network із фізичними відмовами та окремим цифровим блокуванням AM hubs."""

    def __init__(
        self,
        graph: nx.DiGraph,
        suppliers: frozenset,
        consumers: frozenset,
        base_capacities: dict[tuple, float],
        node_supply: dict,
        node_demand: dict,
        digital_dependencies: dict[str, set[str]],
        intervention_catalog: dict[str, list[MaterialRelation | DigitalRelation]],
        metadata: dict[str, Any],
    ) -> None:
        super().__init__(
            graph=graph,
            suppliers=suppliers,
            consumers=consumers,
            base_capacities=base_capacities,
            node_supply=node_supply,
            node_demand=node_demand,
        )
        self.digital_dependencies = {
            hub: set(services) for hub, services in digital_dependencies.items()
        }
        self.intervention_catalog = {
            category: list(relations)
            for category, relations in intervention_catalog.items()
        }
        self.am_metadata = dict(metadata)
        self.physical_failed_nodes: set[str] = set()
        self.failed_digital_services: set[str] = set()
        self.dependency_blocked_nodes: set[str] = set()
        self.applied_relations: list[MaterialRelation | DigitalRelation] = []
        self.refresh_operational_state()

    def nodes_by_role(self, role: str) -> list[str]:
        """Повертає стабільно відсортовані вузли заданої технологічної ролі."""
        return sorted(
            node for node, data in self.graph.nodes(data=True)
            if data.get("role") == role
        )

    def refresh_operational_state(self) -> None:
        """Синхронізує base Network state з фізичними й цифровими відмовами."""
        self.dependency_blocked_nodes = dependency_blocked_hubs(
            self.digital_dependencies,
            self.failed_digital_services,
        )
        combined = (
            set(self.physical_failed_nodes)
            | set(self.failed_digital_services)
            | set(self.dependency_blocked_nodes)
        )
        self.failed_nodes = combined
        for node in self.graph.nodes:
            if node in combined:
                self.node_supply[node] = 0.0
                self.node_demand[node] = 0.0
            else:
                self.node_supply[node] = self._base_supply.get(node, 0.0)
                self.node_demand[node] = self._base_demand.get(node, 0.0)

    def fail_physical(self, node: str) -> None:
        """Позначає фізичний технологічний вузол пошкодженим."""
        self._require_node(node)
        if self.graph.nodes[node].get("role") == "digital_service":
            raise ValueError("Для digital_service використовуйте fail_digital_service().")
        self.physical_failed_nodes.add(node)
        self.refresh_operational_state()

    def repair_physical(self, node: str) -> None:
        """Відновлює фізичний вузол; цифрове блокування при цьому зберігається."""
        self._require_node(node)
        self.physical_failed_nodes.discard(node)
        self.refresh_operational_state()

    def fail_digital_service(self, service: str) -> None:
        """Вимикає цифровий сервіс і каскадно блокує залежні AM hubs."""
        self._require_role(service, "digital_service")
        self.failed_digital_services.add(service)
        self.refresh_operational_state()

    def repair_digital_service(self, service: str) -> None:
        """Відновлює сервіс і автоматично знімає залежні каскадні блокування."""
        self._require_role(service, "digital_service")
        self.failed_digital_services.discard(service)
        self.refresh_operational_state()

    def repairable_nodes(self) -> set[str]:
        """Повертає лише реально пошкоджені елементи, не dependency-blocked hubs."""
        return set(self.physical_failed_nodes) | set(self.failed_digital_services)

    def add_material_relation(self, relation: MaterialRelation) -> None:
        """Активує нову кваліфіковану material-flow relation."""
        if self.graph.has_edge(relation.source, relation.target):
            raise ValueError(
                f"Material relation вже активна: {relation.source}->{relation.target}."
            )
        source_role = self.graph.nodes[relation.source].get("role")
        target_role = self.graph.nodes[relation.target].get("role")
        if (source_role, target_role) not in MATERIAL_RELATIONS:
            raise ValueError(
                f"Некоректна технологічна relation: {source_role}->{target_role}."
            )
        self.graph.add_edge(
            relation.source,
            relation.target,
            relation_category=relation.category,
        )
        edge = (relation.source, relation.target)
        self._base_capacities[edge] = float(relation.capacity)
        self.edge_capacities[edge] = float(relation.capacity)
        self.applied_relations.append(relation)

    def add_digital_relation(self, relation: DigitalRelation) -> None:
        """Активує backup digital enabling relation."""
        self._require_role(relation.service, "digital_service")
        self._require_role(relation.hub, "am_hub")
        if relation.service in self.digital_dependencies[relation.hub]:
            raise ValueError(
                f"Digital relation вже активна: {relation.service}->{relation.hub}."
            )
        add_digital_backup(
            self.digital_dependencies,
            hub=relation.hub,
            service=relation.service,
        )
        self.applied_relations.append(relation)
        self.refresh_operational_state()

    def copy(self) -> "AMNetwork":
        """Повертає незалежну AMNetwork-копію з усіма dependency states."""
        net = AMNetwork(
            graph=self.graph.copy(),
            suppliers=self.suppliers,
            consumers=self.consumers,
            base_capacities=self._base_capacities,
            node_supply=self._base_supply,
            node_demand=self._base_demand,
            digital_dependencies=self.digital_dependencies,
            intervention_catalog=self.intervention_catalog,
            metadata=self.am_metadata,
        )
        net.edge_capacities = dict(self.edge_capacities)
        net.physical_failed_nodes = set(self.physical_failed_nodes)
        net.failed_digital_services = set(self.failed_digital_services)
        net.applied_relations = list(self.applied_relations)
        net.refresh_operational_state()
        return net

    def _require_node(self, node: str) -> None:
        if node not in self.graph:
            raise KeyError(f"Невідомий AM1 node: {node!r}.")

    def _require_role(self, node: str, role: str) -> None:
        self._require_node(node)
        actual = self.graph.nodes[node].get("role")
        if actual != role:
            raise ValueError(f"Node {node!r} має role={actual!r}, очікується {role!r}.")


def generate_am_network(N: int, seed: int) -> AMNetwork:
    """Генерує базову типізовану AM-мережу для N=50 або N=80."""
    if N not in ROLE_COUNTS:
        raise ValueError(f"AM1 підтримує N={sorted(ROLE_COUNTS)}, отримано N={N}.")

    rng = np.random.default_rng(seed)
    counts = ROLE_COUNTS[N]
    nodes = {
        role: [f"{_role_prefix(role)}_{idx:02d}" for idx in range(count)]
        for role, count in counts.items()
    }
    graph = nx.DiGraph()
    n_regions = 4 if N == 50 else 6
    for role, role_nodes in nodes.items():
        for idx, node in enumerate(role_nodes):
            graph.add_node(
                node,
                role=role,
                region=f"region_{idx % n_regions}",
                qualification_group=f"q_{idx % 2}",
            )

    capacities: dict[tuple[str, str], float] = {}
    _connect_primary_stage(
        graph, capacities, rng,
        nodes["feedstock_supplier"], nodes["preprocessing"],
        "feedstock",
    )
    _connect_primary_stage(
        graph, capacities, rng,
        nodes["preprocessing"], nodes["am_hub"],
        "cross_qualification",
    )
    _connect_primary_stage(
        graph, capacities, rng,
        nodes["am_hub"], nodes["post_processing"],
        "downstream",
    )
    _connect_primary_stage(
        graph, capacities, rng,
        nodes["post_processing"], nodes["quality_assurance"],
        "downstream",
    )
    _connect_primary_stage(
        graph, capacities, rng,
        nodes["quality_assurance"], nodes["demand"],
        "demand_delivery",
    )

    node_supply = {node: 0.0 for node in graph.nodes}
    node_demand = {node: 0.0 for node in graph.nodes}
    demand_per_node = 25.0
    for node in nodes["demand"]:
        node_demand[node] = demand_per_node
    total_demand = demand_per_node * len(nodes["demand"])
    supply_per_node = 1.2 * total_demand / len(nodes["feedstock_supplier"])
    for node in nodes["feedstock_supplier"]:
        node_supply[node] = supply_per_node

    primary_service, backup_service = nodes["digital_service"]
    digital_dependencies = {
        hub: {primary_service} for hub in nodes["am_hub"]
    }
    catalog = _build_intervention_catalog(
        graph=graph,
        rng=rng,
        nodes=nodes,
        backup_service=backup_service,
    )
    network = AMNetwork(
        graph=graph,
        suppliers=frozenset(nodes["feedstock_supplier"]),
        consumers=frozenset(nodes["demand"]),
        base_capacities=capacities,
        node_supply=node_supply,
        node_demand=node_demand,
        digital_dependencies=digital_dependencies,
        intervention_catalog=catalog,
        metadata={
            "series": "AM1",
            "N": N,
            "seed": seed,
            "primary_digital_service": primary_service,
            "backup_digital_service": backup_service,
            "intervention_budget": INTERVENTION_BUDGET[N],
        },
    )
    _validate_generated_network(network)
    return network


def apply_architecture(base: AMNetwork, architecture: str) -> AMNetwork:
    """Повертає копію базової мережі з AM1 architecture intervention."""
    if architecture not in ARCHITECTURES:
        raise ValueError(
            f"Невідома AM1 architecture {architecture!r}; доступні {sorted(ARCHITECTURES)}."
        )
    network = base.copy()
    budget = int(network.am_metadata["intervention_budget"])
    if architecture == "A0_baseline":
        network.am_metadata["architecture"] = architecture
        return network

    category_map = {
        "A1_feedstock": ["feedstock"],
        "A2_cross_qualification": ["cross_qualification"],
        "A3_downstream": ["downstream"],
        "A4_digital": ["digital"],
    }
    if architecture == "A5_balanced":
        categories = ["feedstock", "cross_qualification", "downstream", "digital"]
        per_category = budget // len(categories)
        selected = [
            relation
            for category in categories
            for relation in network.intervention_catalog[category][:per_category]
        ]
    else:
        category = category_map[architecture][0]
        selected = network.intervention_catalog[category][:budget]

    if len(selected) != budget:
        raise RuntimeError(
            f"Недостатньо candidate relations для {architecture}: "
            f"потрібно {budget}, доступно {len(selected)}."
        )
    for relation in selected:
        if isinstance(relation, MaterialRelation):
            network.add_material_relation(relation)
        else:
            network.add_digital_relation(relation)
    network.am_metadata["architecture"] = architecture
    network.am_metadata["applied_budget"] = len(selected)
    return network


def _role_prefix(role: str) -> str:
    return {
        "feedstock_supplier": "fs",
        "preprocessing": "pre",
        "am_hub": "am",
        "post_processing": "post",
        "quality_assurance": "qa",
        "demand": "dem",
        "digital_service": "dig",
    }[role]


def _connect_primary_stage(
    graph: nx.DiGraph,
    capacities: dict[tuple[str, str], float],
    rng: np.random.Generator,
    sources: list[str],
    targets: list[str],
    category: str,
) -> None:
    """Дає кожному target один primary predecessor і валідний stage edge."""
    for idx, target in enumerate(targets):
        source = sources[idx % len(sources)]
        source_role = graph.nodes[source]["role"]
        target_role = graph.nodes[target]["role"]
        low, high = CAPACITY_RANGES[(source_role, target_role)]
        capacity = float(rng.uniform(low, high))
        graph.add_edge(source, target, relation_category=category)
        capacities[(source, target)] = capacity


def _build_intervention_catalog(
    graph: nx.DiGraph,
    rng: np.random.Generator,
    nodes: dict[str, list[str]],
    backup_service: str,
) -> dict[str, list[MaterialRelation | DigitalRelation]]:
    """Формує детермінований каталог неактивних relations для paired variants."""
    catalog: dict[str, list[MaterialRelation | DigitalRelation]] = {
        "feedstock": [],
        "cross_qualification": [],
        "downstream": [],
        "digital": [],
    }
    material_specs = [
        ("feedstock", "feedstock_supplier", "preprocessing"),
        ("cross_qualification", "preprocessing", "am_hub"),
    ]
    for category, source_role, target_role in material_specs:
        candidates: list[MaterialRelation] = []
        low, high = CAPACITY_RANGES[(source_role, target_role)]
        for target in nodes[target_role]:
            for source in nodes[source_role]:
                if graph.has_edge(source, target):
                    continue
                candidates.append(
                    MaterialRelation(
                        source=source,
                        target=target,
                        capacity=float(rng.uniform(low, high)),
                        category=category,
                    )
                )
        rng.shuffle(candidates)
        catalog[category].extend(candidates)

    # Downstream budget must cover both constrained stages instead of being
    # consumed only by the much larger AM→post-processing candidate pool.
    downstream_pools: list[list[MaterialRelation]] = []
    for source_role, target_role in [
        ("am_hub", "post_processing"),
        ("post_processing", "quality_assurance"),
    ]:
        candidates = []
        low, high = CAPACITY_RANGES[(source_role, target_role)]
        for target in nodes[target_role]:
            for source in nodes[source_role]:
                if graph.has_edge(source, target):
                    continue
                candidates.append(
                    MaterialRelation(
                        source=source,
                        target=target,
                        capacity=float(rng.uniform(low, high)),
                        category="downstream",
                    )
                )
        rng.shuffle(candidates)
        downstream_pools.append(candidates)
    catalog["downstream"] = _round_robin_relations(downstream_pools)

    digital_candidates = [
        DigitalRelation(service=backup_service, hub=hub)
        for hub in nodes["am_hub"]
    ]
    rng.shuffle(digital_candidates)
    catalog["digital"] = digital_candidates
    return catalog


def _round_robin_relations(
    pools: list[list[MaterialRelation]],
) -> list[MaterialRelation]:
    """Чергує candidate pools, зберігаючи seeded order усередині кожного."""
    result: list[MaterialRelation] = []
    max_length = max((len(pool) for pool in pools), default=0)
    for idx in range(max_length):
        for pool in pools:
            if idx < len(pool):
                result.append(pool[idx])
    return result


def _validate_generated_network(network: AMNetwork) -> None:
    """Перевіряє role counts, stage legality та end-to-end reachability."""
    expected = ROLE_COUNTS[network.N]
    actual = {
        role: len(network.nodes_by_role(role)) for role in expected
    }
    if actual != expected:
        raise RuntimeError(f"Некоректні AM1 role counts: {actual}, очікується {expected}.")
    for source, target in network.graph.edges:
        relation = (
            network.graph.nodes[source].get("role"),
            network.graph.nodes[target].get("role"),
        )
        if relation not in MATERIAL_RELATIONS:
            raise RuntimeError(f"Некоректний material edge {source}->{target}: {relation}.")
    for demand in network.consumers:
        if not any(
            nx.has_path(network.graph, supplier, demand)
            for supplier in network.suppliers
        ):
            raise RuntimeError(f"Demand node {demand!r} не має end-to-end route.")
    min_budget = int(network.am_metadata["intervention_budget"])
    for category, relations in network.intervention_catalog.items():
        if len(relations) < min_budget:
            raise RuntimeError(
                f"Catalog {category!r} має {len(relations)} candidates, потрібно {min_budget}."
            )
