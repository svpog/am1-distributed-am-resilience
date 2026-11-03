"""Тести автоматичного аудиту AM1 calibration-gates."""

import pandas as pd

from src.am1.calibration import audit_calibration


def _valid_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_rows = []
    q_rows = []
    for run_idx in range(2):
        paired_id = f"p{run_idx}"
        for architecture in ("A0", "A1"):
            raw_rows.append(
                {
                    "architecture": architecture,
                    "disruption": "D1",
                    "paired_run_id": paired_id,
                    "network_seed": run_idx,
                    "disruption_seed": 10 + run_idx,
                    "recovery_seed": 20 + run_idx,
                    "selected_disruption_target": '["am_00"]',
                    "valid": True,
                    "rho": 0.8,
                    "robustness": 0.4,
                    "final_recovery": 1.0,
                    "non_recovered": False,
                    "runtime_seconds": 0.01,
                }
            )
            for t, q_value in enumerate((1.0, 0.4, 1.0)):
                q_rows.append(
                    {
                        "architecture": architecture,
                        "disruption": "D1",
                        "paired_run_id": paired_id,
                        "t": t,
                        "Q": q_value,
                    }
                )
    return pd.DataFrame(raw_rows), pd.DataFrame(q_rows)


def test_valid_calibration_passes_all_stop_gates() -> None:
    raw, q_curves = _valid_fixture()
    summary, cells = audit_calibration(
        raw,
        q_curves,
        architectures=("A0", "A1"),
        disruptions=("D1",),
        n_runs=2,
        T_max=2,
    )

    assert summary["all_stop_gates_pass"] is True
    assert summary["paired_integrity"] is True
    assert summary["q_curve_integrity"] is True
    assert len(cells) == 2


def test_seed_mismatch_fails_paired_integrity() -> None:
    raw, q_curves = _valid_fixture()
    raw.loc[(raw["paired_run_id"] == "p0") & (raw["architecture"] == "A1"), "network_seed"] = 999

    summary, _ = audit_calibration(
        raw,
        q_curves,
        architectures=("A0", "A1"),
        disruptions=("D1",),
        n_runs=2,
        T_max=2,
    )

    assert summary["paired_integrity"] is False
    assert summary["all_stop_gates_pass"] is False


def test_short_q_curve_and_low_recovery_fail_gates() -> None:
    raw, q_curves = _valid_fixture()
    raw["final_recovery"] = 0.8
    raw["non_recovered"] = True
    q_curves = q_curves.iloc[:-1]

    summary, _ = audit_calibration(
        raw,
        q_curves,
        architectures=("A0", "A1"),
        disruptions=("D1",),
        n_runs=2,
        T_max=2,
    )

    assert summary["horizon_T_sufficient"] is False
    assert summary["q_curve_integrity"] is False
    assert summary["all_stop_gates_pass"] is False
