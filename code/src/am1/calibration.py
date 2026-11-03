"""Автоматичний аудит calibration-gates серії AM1.

Звіт перевіряє повноту факторного плану, paired integrity, валідність,
достатність горизонту T та ознаки тривіального насичення. Порогові значення
використовуються лише як stop-gates протоколу, а не для підбору бажаного
ранжування архітектур.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


def audit_calibration(
    raw: pd.DataFrame,
    q_curves: pd.DataFrame,
    architectures: Iterable[str],
    disruptions: Iterable[str],
    n_runs: int,
    T_max: int,
    target: float = 0.95,
    alpha: float = 0.10,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Повертає machine-readable summary і діагностику кожної A×D cell."""
    architectures = tuple(architectures)
    disruptions = tuple(disruptions)
    expected_rows = len(architectures) * len(disruptions) * n_runs
    expected_q_rows = expected_rows * (T_max + 1)

    key = ["architecture", "disruption"]
    cells = (
        raw.groupby(key, as_index=False)
        .agg(
            n_rows=("paired_run_id", "size"),
            n_pairs=("paired_run_id", "nunique"),
            invalid_share=("valid", lambda values: 1.0 - float(np.mean(values))),
            rho_median=("rho", "median"),
            robustness_median=("robustness", "median"),
            final_recovery_median=("final_recovery", "median"),
            recovered_share=("final_recovery", lambda values: float(np.mean(values >= target))),
            non_recovered_share=("non_recovered", "mean"),
            ineffective_disruption_share=("robustness", lambda values: float(np.mean(values >= 0.999))),
            runtime_median_seconds=("runtime_seconds", "median"),
        )
        .sort_values(key)
        .reset_index(drop=True)
    )
    cvar = (
        raw[raw["valid"]]
        .groupby(key)["rho"]
        .apply(lambda values: _lower_tail_mean(values, alpha))
        .rename(f"rho_CVaR_{alpha:.2f}")
        .reset_index()
    )
    cells = cells.merge(cvar, on=key, how="left")

    paired = raw.groupby(["disruption", "paired_run_id"], as_index=False).agg(
        n_architectures=("architecture", "nunique"),
        n_network_seeds=("network_seed", "nunique"),
        n_disruption_seeds=("disruption_seed", "nunique"),
        n_recovery_seeds=("recovery_seed", "nunique"),
        n_targets=("selected_disruption_target", "nunique"),
    )
    pair_ok = (
        paired["n_architectures"].eq(len(architectures))
        & paired["n_network_seeds"].eq(1)
        & paired["n_disruption_seeds"].eq(1)
        & paired["n_recovery_seeds"].eq(1)
        & paired["n_targets"].eq(1)
    )
    q_group_sizes = q_curves.groupby(
        ["architecture", "disruption", "paired_run_id"]
    ).size()

    observed_cells = set(map(tuple, raw[key].drop_duplicates().to_numpy()))
    expected_cells = {(a, d) for a in architectures for d in disruptions}
    invalid_gate = bool((cells["invalid_share"] <= 0.05).all())
    horizon_gate = bool((cells["recovered_share"] >= 0.50).all())
    paired_gate = bool(len(paired) == len(disruptions) * n_runs and pair_ok.all())
    q_gate = bool(
        len(q_curves) == expected_q_rows
        and len(q_group_sizes) == expected_rows
        and q_group_sizes.eq(T_max + 1).all()
    )
    factorial_gate = bool(
        len(raw) == expected_rows
        and observed_cells == expected_cells
        and cells["n_rows"].eq(n_runs).all()
    )

    saturation_cells = cells.loc[
        cells["ineffective_disruption_share"] >= 0.80,
        key + ["ineffective_disruption_share"],
    ].to_dict("records")
    summary: dict[str, Any] = {
        "expected_raw_rows": expected_rows,
        "observed_raw_rows": int(len(raw)),
        "expected_q_rows": expected_q_rows,
        "observed_q_rows": int(len(q_curves)),
        "factorial_complete": factorial_gate,
        "paired_integrity": paired_gate,
        "q_curve_integrity": q_gate,
        "invalid_share_gate": invalid_gate,
        "horizon_T_sufficient": horizon_gate,
        "max_invalid_share": float(cells["invalid_share"].max()),
        "min_recovered_share": float(cells["recovered_share"].min()),
        "saturation_cells": saturation_cells,
        "median_runtime_seconds_per_run": float(raw["runtime_seconds"].median()),
        "total_runtime_seconds_recorded": float(raw["runtime_seconds"].sum()),
    }
    summary["all_stop_gates_pass"] = all(
        summary[name]
        for name in (
            "factorial_complete",
            "paired_integrity",
            "q_curve_integrity",
            "invalid_share_gate",
            "horizon_T_sufficient",
        )
    )
    return summary, cells


def write_calibration_report(
    raw_path: str | Path,
    q_path: str | Path,
    report_dir: str | Path,
    architectures: Iterable[str],
    disruptions: Iterable[str],
    n_runs: int,
    T_max: int,
    target: float = 0.95,
    alpha: float = 0.10,
) -> dict[str, Path]:
    """Читає immutable raw outputs і зберігає JSON, TXT та cell diagnostics."""
    raw = pd.read_csv(raw_path)
    q_curves = pd.read_csv(q_path)
    summary, cells = audit_calibration(
        raw,
        q_curves,
        architectures=architectures,
        disruptions=disruptions,
        n_runs=n_runs,
        T_max=T_max,
        target=target,
        alpha=alpha,
    )
    destination = Path(report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "calibration_report.json"
    text_path = destination / "calibration_report.txt"
    cells_path = destination / "calibration_cell_diagnostics.csv"
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    cells.to_csv(cells_path, index=False)
    text_path.write_text(_format_text_report(summary), encoding="utf-8")
    return {"calibration_json": json_path, "calibration_text": text_path, "calibration_cells": cells_path}


def _lower_tail_mean(values: pd.Series, alpha: float) -> float:
    ordered = np.sort(values.dropna().to_numpy(dtype=float))
    if len(ordered) == 0:
        return math.nan
    count = max(1, int(math.ceil(alpha * len(ordered))))
    return float(np.mean(ordered[:count]))


def _format_text_report(summary: dict[str, Any]) -> str:
    status = "PASS" if summary["all_stop_gates_pass"] else "STOP"
    lines = [
        "AM1 calibration gate report",
        f"Overall decision: {status}",
        f"Factorial completeness: {summary['factorial_complete']}",
        f"Paired integrity: {summary['paired_integrity']}",
        f"Q-curve integrity: {summary['q_curve_integrity']}",
        f"Invalid-share gate: {summary['invalid_share_gate']} (max={summary['max_invalid_share']:.4f})",
        f"T horizon sufficient: {summary['horizon_T_sufficient']} (min recovered share={summary['min_recovered_share']:.4f})",
        f"Saturation cells (diagnostic, not tuned): {len(summary['saturation_cells'])}",
        f"Median runtime per run: {summary['median_runtime_seconds_per_run']:.6f} s",
        f"Recorded total runtime: {summary['total_runtime_seconds_recorded']:.3f} s",
    ]
    return "\n".join(lines) + "\n"
