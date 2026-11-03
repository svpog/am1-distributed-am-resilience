"""Цифрові enabling dependencies для AM1.

Матеріальний потік проходить лише через фізичні технологічні стадії. Цифрові
сервіси не є матеріальними вузлами маршруту: вони визначають, чи може AM hub
працювати. Вузол AM блокується, лише якщо всі призначені йому цифрові сервіси
недоступні.
"""

from __future__ import annotations

from collections.abc import Mapping, Set


def dependency_blocked_hubs(
    digital_dependencies: Mapping[str, Set[str]],
    failed_services: Set[str],
) -> set[str]:
    """Повертає AM hubs, у яких не лишилося активного цифрового сервісу."""
    blocked: set[str] = set()
    for hub, services in digital_dependencies.items():
        if not services:
            raise ValueError(f"AM hub {hub!r} не має цифрової enabling dependency.")
        if services.issubset(failed_services):
            blocked.add(hub)
    return blocked


def add_digital_backup(
    digital_dependencies: dict[str, set[str]],
    hub: str,
    service: str,
) -> None:
    """Додає резервний цифровий сервіс для AM hub без дублювання relation."""
    if hub not in digital_dependencies:
        raise KeyError(f"Невідомий AM hub для digital backup: {hub!r}.")
    digital_dependencies[hub].add(service)
