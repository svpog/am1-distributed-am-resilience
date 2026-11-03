"""Ізольований paired Monte Carlo runner серії AM1.

Модуль записує результати виключно в ``raw/am1``, ``aggregated/am1`` і
``reports/am1`` усередині явно переданого output root. Наявні runner-и та
каталоги попередніх статей не використовуються й не змінюються.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.am1.disruptions import (
    apply_primary_digital_outage,
    apply_printer_random_fixed_budget,
    apply_regional_cluster,
    apply_targeted_role_failure,
    select_targeted_role_node,
)
from src.am1.flow import compute_am_max_flow as compute_max_flow
from src.am1.network import (
    ARCHITECTURES,
    ROLE_COUNTS,
    AMNetwork,
    apply_architecture,
    generate_am_network,
)
from src.am1.recovery import RandomAMRecovery, get_am_recovery
from src.metrics.integral import compute_integral_metrics


DISRUPTIONS = {
    "D1_printer_random",
    "D2_feedstock_targeted",
    "D3_postprocess_targeted",
    "D4_digital_outage",
    "D5_regional_cluster",
}


@dataclass(frozen=True)
class Plan:
    """Валідований execution plan із YAML-конфігурації."""

    name: str
    scale: str
    N: int
    n_runs: int
    seed_start: int
    architectures: tuple[str, ...]
    disruptions: tuple[str, ...]


def load_am1_config(path: str | Path = "config/series_AM1.yaml") -> dict[str, Any]:
    """Завантажує AM1 YAML без мутації словника конфігурації."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    if config.get("series") != "AM1":
        raise ValueError(f"Очікується series=AM1 у {config_path}.")
    return config


def resolve_plan(
    config: dict[str, Any],
    plan_name: str,
    runs_override: int | None = None,
) -> Plan:
    """Перетворює plan section на строгий і перевірений ``Plan``."""
    try:
        raw = config["plans"][plan_name]
    except KeyError as exc:
        allowed = sorted(config.get("plans", {}))
        raise ValueError(f"Невідомий AM1 plan {plan_name!r}; доступні {allowed}.") from exc

    n_runs = int(runs_override if runs_override is not None else raw["n_runs"])
    if n_runs <= 0:
        raise ValueError("AM1 n_runs має бути додатним.")
    architectures = tuple(raw.get("architectures", config["architectures"]))
    disruptions = tuple(raw.get("disruptions", config["disruptions"]))
    unknown_a = set(architectures) - ARCHITECTURES
    unknown_d = set(disruptions) - DISRUPTIONS
    if unknown_a or unknown_d:
        raise ValueError(
            f"Некоректний AM1 plan: unknown architectures={sorted(unknown_a)}, "
            f"unknown disruptions={sorted(unknown_d)}."
        )
    return Plan(
        name=plan_name,
        scale=str(raw["scale"]),
        N=int(raw["N"]),
        n_runs=n_runs,
        seed_start=int(raw["seed_start"]),
        architectures=architectures,
        disruptions=disruptions,
    )


def simulate_recovery(
    network: AMNetwork,
    F0: float,
    T_max: int,
    strategy_name: str,
    recovery_seed: int,
    mu: int = 1,
) -> tuple[list[float], list[str]]:
    """Симулює AM1 recovery і повертає Q(t) та порядок repair actions."""
    if T_max <= 0:
        raise ValueError("T_max має бути додатним.")
    if mu != 1:
        raise ValueError("Протокол AM1 фіксує mu=1.")
    recovery = get_am_recovery(strategy_name)
    rng = np.random.default_rng(recovery_seed)
    q_curve = [1.0]
    repaired: list[str] = []

    for t in range(1, T_max + 1):
        q_t = compute_max_flow(network) / F0 if F0 > 0.0 else 0.0
        q_curve.append(float(np.clip(q_t, 0.0, 1.0)))

        if isinstance(recovery, RandomAMRecovery):
            element = recovery.select_element_to_repair(network, t, rng)
        else:
            element = recovery.select_element_to_repair(network, t)
        if element is not None:
            recovery.repair(network, element)
            repaired.append(element)

    return q_curve, repaired


def run_am1(
    config: dict[str, Any],
    plan: Plan,
    output_root: str | Path,
    run_label: str | None = None,
) -> dict[str, Path]:
    """Виконує paired AM1 plan та атомарно створює новий output namespace."""
    started = time.perf_counter()
    config_hash = _config_hash(config)
    git_commit = _current_git_hash()
    git_dirty = _git_is_dirty()
    label = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    paths = _prepare_output_paths(Path(output_root), label)

    recovery_cfg = config["recovery"]
    simulation_cfg = config["simulation"]
    strategy_name = str(recovery_cfg["strategy"])
    mu = int(recovery_cfg["mu"])
    T_max = int(simulation_cfg["T_max"])
    target = float(simulation_cfg["Q_target_frac"])

    raw_rows: list[dict[str, Any]] = []
    q_rows: list[dict[str, Any]] = []
    for disruption in plan.disruptions:
        for run_idx in range(plan.n_runs):
            network_seed = plan.seed_start + run_idx
            disruption_seed = plan.seed_start + plan.n_runs + run_idx
            recovery_seed = plan.seed_start + 2 * plan.n_runs + run_idx
            paired_id = f"{plan.name}-{plan.scale}-{disruption}-{run_idx:04d}"
            base = generate_am_network(plan.N, network_seed)
            shared_target = _shared_target(base, disruption)

            for architecture in plan.architectures:
                run_started = time.perf_counter()
                network = apply_architecture(base, architecture)
                F0 = compute_max_flow(network)
                valid = bool(F0 > 0.0)
                exclusion_reason = "" if valid else "F0_nonpositive"

                if valid:
                    _apply_disruption(
                        network,
                        disruption,
                        disruption_seed,
                        shared_target,
                        config,
                    )
                    physical_failures = len(network.physical_failed_nodes)
                    blocked_hubs = len(network.dependency_blocked_nodes)
                    functionally_lost = len(network.failed_nodes)
                    q_curve, repaired = simulate_recovery(
                        network,
                        F0=F0,
                        T_max=T_max,
                        strategy_name=strategy_name,
                        recovery_seed=recovery_seed,
                        mu=mu,
                    )
                    metrics = compute_integral_metrics(q_curve, t_e=1)
                    t95 = _time_to_target(q_curve, target)
                else:
                    physical_failures = blocked_hubs = functionally_lost = 0
                    q_curve, repaired = [], []
                    metrics = {"rho": math.nan, "R_rb": math.nan, "R_inf": math.nan}
                    t95 = math.nan

                raw_rows.append(
                    {
                        "series": "AM1",
                        "plan": plan.name,
                        "scale": plan.scale,
                        "N": plan.N,
                        "architecture": architecture,
                        "disruption": disruption,
                        "paired_run_id": paired_id,
                        "run_idx": run_idx,
                        "network_seed": network_seed,
                        "graph_seed": network_seed,
                        "capacity_seed": network_seed,
                        "disruption_seed": disruption_seed,
                        "recovery_seed": recovery_seed,
                        "seed_policy": "shared_generator_stream",
                        "intervention_budget": int(network.am_metadata["intervention_budget"]),
                        "applied_budget": len(network.applied_relations),
                        "n_feedstock_suppliers": ROLE_COUNTS[plan.N]["feedstock_supplier"],
                        "n_preprocessing": ROLE_COUNTS[plan.N]["preprocessing"],
                        "n_am_hubs": ROLE_COUNTS[plan.N]["am_hub"],
                        "n_post_processing": ROLE_COUNTS[plan.N]["post_processing"],
                        "n_quality_assurance": ROLE_COUNTS[plan.N]["quality_assurance"],
                        "n_demand": ROLE_COUNTS[plan.N]["demand"],
                        "n_digital_services": ROLE_COUNTS[plan.N]["digital_service"],
                        "recovery_strategy": strategy_name,
                        "mu": mu,
                        "T_max": T_max,
                        "F0": F0,
                        "rho": metrics["rho"],
                        "robustness": metrics["R_rb"],
                        "final_recovery": q_curve[-1] if q_curve else math.nan,
                        "t95": t95,
                        "non_recovered": bool(q_curve[-1] < target) if q_curve else True,
                        "physical_failures": physical_failures,
                        "blocked_hubs": blocked_hubs,
                        "functionally_lost_nodes": functionally_lost,
                        "repaired_elements": len(repaired),
                        "selected_disruption_target": json.dumps(
                            network.disruption_metadata.get("selected", []),
                            ensure_ascii=False,
                        ),
                        "valid": valid,
                        "exclusion_reason": exclusion_reason,
                        "runtime_seconds": time.perf_counter() - run_started,
                        "git_commit": git_commit,
                        "git_dirty": git_dirty,
                        "config_hash": config_hash,
                    }
                )
                for t, q_value in enumerate(q_curve):
                    q_rows.append(
                        {
                            "series": "AM1",
                            "plan": plan.name,
                            "scale": plan.scale,
                            "architecture": architecture,
                            "disruption": disruption,
                            "paired_run_id": paired_id,
                            "t": t,
                            "Q": q_value,
                        }
                    )

    raw_df = pd.DataFrame(raw_rows)
    q_df = pd.DataFrame(q_rows)
    aggregated = _aggregate_smoke(raw_df)
    raw_df.to_csv(paths["raw"] / "raw_results.csv", index=False)
    q_df.to_csv(paths["raw"] / "q_curves.csv", index=False)
    aggregated.to_csv(paths["aggregated"] / "aggregated_results.csv", index=False)
    metadata = {
        "series": "AM1",
        "plan": plan.name,
        "run_label": label,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "config_hash": config_hash,
        "n_raw_rows": len(raw_df),
        "n_q_rows": len(q_df),
        "elapsed_seconds": time.perf_counter() - started,
        "output_root": str(Path(output_root).resolve()),
    }
    (paths["reports"] / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "raw_results": paths["raw"] / "raw_results.csv",
        "q_curves": paths["raw"] / "q_curves.csv",
        "aggregated_results": paths["aggregated"] / "aggregated_results.csv",
        "metadata": paths["reports"] / "metadata.json",
    }


def _shared_target(base: AMNetwork, disruption: str) -> str | None:
    if disruption == "D2_feedstock_targeted":
        return select_targeted_role_node(base, "feedstock_supplier")
    if disruption == "D3_postprocess_targeted":
        return select_targeted_role_node(base, "post_processing")
    return None


def _apply_disruption(
    network: AMNetwork,
    disruption: str,
    seed: int,
    shared_target: str | None,
    config: dict[str, Any],
) -> None:
    if disruption == "D1_printer_random":
        fraction = float(config["disruption"]["printer_failure_fraction"])
        apply_printer_random_fixed_budget(network, seed=seed, fraction=fraction)
    elif disruption == "D2_feedstock_targeted":
        apply_targeted_role_failure(network, "feedstock_supplier", shared_target)
    elif disruption == "D3_postprocess_targeted":
        apply_targeted_role_failure(network, "post_processing", shared_target)
    elif disruption == "D4_digital_outage":
        apply_primary_digital_outage(network)
    elif disruption == "D5_regional_cluster":
        apply_regional_cluster(network, seed=seed)
    else:
        raise ValueError(f"Невідомий AM1 disruption {disruption!r}.")


def _time_to_target(q_curve: list[float], target: float) -> int | float:
    for t in range(1, len(q_curve)):
        if q_curve[t] >= target:
            return t
    return math.nan


def _aggregate_smoke(raw: pd.DataFrame) -> pd.DataFrame:
    valid = raw[raw["valid"]].copy()
    if valid.empty:
        return pd.DataFrame()
    return (
        valid.groupby(["scale", "architecture", "disruption"], as_index=False)
        .agg(
            n_valid=("rho", "size"),
            rho_median=("rho", "median"),
            robustness_median=("robustness", "median"),
            final_recovery_median=("final_recovery", "median"),
            non_recovered_share=("non_recovered", "mean"),
        )
    )


def _prepare_output_paths(root: Path, label: str) -> dict[str, Path]:
    if not label or Path(label).name != label or label in {".", ".."}:
        raise ValueError("run_label має бути безпечною назвою одного каталогу.")
    paths = {
        "raw": root / "raw" / "am1" / label,
        "aggregated": root / "aggregated" / "am1" / label,
        "reports": root / "reports" / "am1" / label,
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError(
            f"AM1 output namespace {label!r} вже існує; raw outputs не переписуються."
        )
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=False)
    return paths


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _current_git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _git_is_dirty() -> bool | None:
    """Фіксує, чи відрізнявся робочий код від записаного commit під час run."""
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(output.strip())
    except (OSError, subprocess.CalledProcessError):
        return None
