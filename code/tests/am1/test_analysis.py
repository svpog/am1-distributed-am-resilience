from __future__ import annotations

import numpy as np
import pandas as pd

from src.am1.analysis import (
    holm_adjust,
    lower_tail_cvar,
    matched_rank_biserial,
    paired_delta_cvar_ci,
)


def test_lower_tail_cvar_uses_exact_floor_tail() -> None:
    values = np.arange(1, 21, dtype=float)
    assert lower_tail_cvar(values, alpha=0.10) == 1.5


def test_paired_bootstrap_is_deterministic() -> None:
    baseline = np.linspace(0.7, 0.9, 40)
    intervention = baseline + 0.01
    first = paired_delta_cvar_ci(baseline, intervention, seed=123, B=100)
    second = paired_delta_cvar_ci(baseline, intervention, seed=123, B=100)
    assert first == second
    assert np.allclose(first, (0.01, 0.01))


def test_rank_biserial_direction() -> None:
    assert matched_rank_biserial(np.array([1.0, 2.0, 3.0])) == 1.0
    assert matched_rank_biserial(np.array([-1.0, -2.0])) == -1.0
    assert matched_rank_biserial(np.zeros(4)) == 0.0


def test_holm_adjustment_is_monotone_in_sorted_order() -> None:
    raw = pd.Series([0.04, 0.001, 0.02, 0.2])
    adjusted = holm_adjust(raw)
    ordered = adjusted.iloc[np.argsort(raw.to_numpy())].to_numpy()
    assert np.all(np.diff(ordered) >= 0)
    assert np.all((adjusted >= raw) & (adjusted <= 1.0))
