"""Regression-тест рідкісного NetworkX preflow-push edge case в AM1."""

from src.am1.flow import compute_am_max_flow
from src.am1.network import apply_architecture, generate_am_network


def test_am_flow_fallback_handles_full_run_seed_920176() -> None:
    network = apply_architecture(
        generate_am_network(N=50, seed=920176),
        "A2_cross_qualification",
    )

    value = compute_am_max_flow(network)

    assert value > 0.0
