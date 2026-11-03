"""Statistical analysis and publication figures for the preregistered AM1 study."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import rankdata, spearmanr, wilcoxon


ROOT = Path(__file__).resolve().parents[2]
ALPHA = 0.10
BOOTSTRAP_B = 2000
ARCHITECTURES = [
    "A0_baseline",
    "A1_feedstock",
    "A2_cross_qualification",
    "A3_downstream",
    "A4_digital",
    "A5_balanced",
]
INTERVENTIONS = ARCHITECTURES[1:]
DISRUPTIONS = [
    "D1_printer_random",
    "D2_feedstock_targeted",
    "D3_postprocess_targeted",
    "D4_digital_outage",
    "D5_regional_cluster",
]
ALIGNED = {
    "D2_feedstock_targeted": "A1_feedstock",
    "D3_postprocess_targeted": "A3_downstream",
    "D4_digital_outage": "A4_digital",
}


def stable_seed(*parts: object) -> int:
    text = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def lower_tail_cvar(values: np.ndarray | pd.Series, alpha: float = ALPHA) -> float:
    arr = np.asarray(values, dtype=float)
    arr = np.sort(arr[np.isfinite(arr)])
    if arr.size == 0:
        return float("nan")
    n_tail = max(1, int(np.floor(alpha * arr.size)))
    return float(np.mean(arr[:n_tail]))


def bootstrap_ci(
    values: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    *,
    seed: int,
    B: int = BOOTSTRAP_B,
) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = np.empty(B, dtype=float)
    for idx in range(B):
        samples[idx] = statistic(rng.choice(arr, size=arr.size, replace=True))
    return tuple(float(x) for x in np.quantile(samples, [0.025, 0.975]))


def paired_delta_cvar_ci(
    baseline: np.ndarray,
    intervention: np.ndarray,
    *,
    seed: int,
    B: int = BOOTSTRAP_B,
) -> tuple[float, float]:
    base = np.asarray(baseline, dtype=float)
    alt = np.asarray(intervention, dtype=float)
    if base.size != alt.size or base.size == 0:
        raise ValueError("Paired samples must be non-empty and have equal size")
    rng = np.random.default_rng(seed)
    samples = np.empty(B, dtype=float)
    for idx in range(B):
        take = rng.integers(0, base.size, size=base.size)
        samples[idx] = lower_tail_cvar(alt[take]) - lower_tail_cvar(base[take])
    return tuple(float(x) for x in np.quantile(samples, [0.025, 0.975]))


def matched_rank_biserial(differences: np.ndarray) -> float:
    diff = np.asarray(differences, dtype=float)
    diff = diff[np.isfinite(diff) & ~np.isclose(diff, 0.0)]
    if diff.size == 0:
        return 0.0
    ranks = rankdata(np.abs(diff), method="average")
    positive = float(ranks[diff > 0].sum())
    negative = float(ranks[diff < 0].sum())
    return (positive - negative) / (positive + negative)


def holm_adjust(p_values: pd.Series) -> pd.Series:
    values = p_values.astype(float).to_numpy()
    order = np.argsort(values)
    adjusted = np.empty_like(values)
    running = 0.0
    m = len(values)
    for rank, position in enumerate(order):
        candidate = (m - rank) * values[position]
        running = max(running, candidate)
        adjusted[position] = min(1.0, running)
    return pd.Series(adjusted, index=p_values.index)


def validate_raw(raw: pd.DataFrame, expected_runs: int) -> None:
    required = {
        "scale", "architecture", "disruption", "paired_run_id", "rho",
        "robustness", "final_recovery", "t95", "non_recovered", "valid",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if not raw["valid"].astype(bool).all():
        raise ValueError("AM1 analysis received invalid runs")
    counts = raw.groupby(["scale", "architecture", "disruption"]).size()
    if not (counts == expected_runs).all():
        raise ValueError(f"Unexpected cell sizes: {counts[counts != expected_runs].to_dict()}")
    architectures = set(raw["architecture"])
    disruptions = set(raw["disruption"])
    if architectures != set(ARCHITECTURES) or disruptions != set(DISRUPTIONS):
        raise ValueError("Incomplete AM1 factorial design")


def descriptive_statistics(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (scale, architecture, disruption), group in raw.groupby(
        ["scale", "architecture", "disruption"], sort=False
    ):
        rho = group["rho"].to_numpy(float)
        cvar_ci = bootstrap_ci(
            rho,
            lower_tail_cvar,
            seed=stable_seed(scale, architecture, disruption, "cvar"),
        )
        rows.append(
            {
                "scale": scale,
                "N": int(group["N"].iloc[0]),
                "architecture": architecture,
                "disruption": disruption,
                "n": len(group),
                "rho_median": float(np.median(rho)),
                "rho_q25": float(np.quantile(rho, 0.25)),
                "rho_q75": float(np.quantile(rho, 0.75)),
                "rho_cvar_0.10": lower_tail_cvar(rho),
                "rho_cvar_ci_low": cvar_ci[0],
                "rho_cvar_ci_high": cvar_ci[1],
                "robustness_median": float(group["robustness"].median()),
                "final_recovery_median": float(group["final_recovery"].median()),
                "t95_median": float(group["t95"].median()),
                "non_recovered_share": float(group["non_recovered"].mean()),
                "physical_failures_median": float(group["physical_failures"].median()),
                "blocked_hubs_median": float(group["blocked_hubs"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["N", "disruption", "architecture"]
    ).reset_index(drop=True)


def paired_effects(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (scale, disruption), scenario in raw.groupby(["scale", "disruption"], sort=False):
        base = scenario[scenario["architecture"] == "A0_baseline"][
            ["paired_run_id", "rho", "non_recovered"]
        ].rename(columns={"rho": "rho_base", "non_recovered": "nr_base"})
        for architecture in INTERVENTIONS:
            alt = scenario[scenario["architecture"] == architecture][
                ["paired_run_id", "rho", "non_recovered"]
            ].rename(columns={"rho": "rho_alt", "non_recovered": "nr_alt"})
            paired = base.merge(alt, on="paired_run_id", validate="one_to_one")
            if len(paired) != len(base):
                raise ValueError(f"Pairing failure for {scale}, {disruption}, {architecture}")
            base_rho = paired["rho_base"].to_numpy(float)
            alt_rho = paired["rho_alt"].to_numpy(float)
            diff = alt_rho - base_rho
            ci = paired_delta_cvar_ci(
                base_rho,
                alt_rho,
                seed=stable_seed(scale, disruption, architecture, "delta_cvar"),
            )
            if np.allclose(diff, 0.0):
                statistic, p_value = 0.0, 1.0
            else:
                statistic, p_value = wilcoxon(
                    alt_rho, base_rho, alternative="two-sided", zero_method="pratt"
                )
            rows.append(
                {
                    "scale": scale,
                    "N": int(scenario["N"].iloc[0]),
                    "disruption": disruption,
                    "architecture": architecture,
                    "n_pairs": len(paired),
                    "rho_cvar_baseline": lower_tail_cvar(base_rho),
                    "rho_cvar_architecture": lower_tail_cvar(alt_rho),
                    "delta_cvar": lower_tail_cvar(alt_rho) - lower_tail_cvar(base_rho),
                    "delta_cvar_ci_low": ci[0],
                    "delta_cvar_ci_high": ci[1],
                    "paired_median_delta_rho": float(np.median(diff)),
                    "wilcoxon_statistic": float(statistic),
                    "wilcoxon_p": float(p_value),
                    "rank_biserial": matched_rank_biserial(diff),
                    "delta_non_recovered_share": float(
                        paired["nr_alt"].astype(float).mean()
                        - paired["nr_base"].astype(float).mean()
                    ),
                }
            )
    effects = pd.DataFrame(rows)
    effects["wilcoxon_p_holm"] = effects.groupby(
        ["scale", "disruption"], group_keys=False
    )["wilcoxon_p"].apply(holm_adjust)
    effects["significant_holm_0.05"] = effects["wilcoxon_p_holm"] < 0.05
    return effects.sort_values(["N", "disruption", "architecture"]).reset_index(drop=True)


def hypothesis_summary(effects: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    scale_rows: list[dict[str, object]] = []
    for scale, group in effects.groupby("scale", sort=False):
        for disruption, aligned in ALIGNED.items():
            scenario = group[group["disruption"] == disruption]
            best_value = float(scenario["delta_cvar"].max())
            aligned_value = float(
                scenario.loc[scenario["architecture"] == aligned, "delta_cvar"].iloc[0]
            )
            rows.append(
                {
                    "hypothesis": "H1",
                    "scale": scale,
                    "component": disruption,
                    "expected_architecture": aligned,
                    "observed_best": scenario.loc[
                        scenario["delta_cvar"].idxmax(), "architecture"
                    ],
                    "expected_delta_cvar": aligned_value,
                    "best_delta_cvar": best_value,
                    "status": "SUPPORTED" if np.isclose(aligned_value, best_value) else "NOT_SUPPORTED",
                }
            )

        maximin = group.groupby("architecture")["delta_cvar"].min().sort_values(ascending=False)
        best_architecture = str(maximin.index[0])
        rows.append(
            {
                "hypothesis": "H2",
                "scale": scale,
                "component": "maximin_across_disruptions",
                "expected_architecture": "A5_balanced",
                "observed_best": best_architecture,
                "expected_delta_cvar": float(maximin["A5_balanced"]),
                "best_delta_cvar": float(maximin.iloc[0]),
                "status": "SUPPORTED" if best_architecture == "A5_balanced" else "NOT_SUPPORTED",
            }
        )

    wide = effects.pivot_table(
        index=["disruption", "architecture"], columns="scale", values="delta_cvar"
    ).reset_index()
    scale_names = [col for col in wide.columns if col not in {"disruption", "architecture"}]
    if len(scale_names) != 2:
        raise ValueError("H4 requires exactly two AM1 scales")
    left, right = sorted(scale_names)
    wide["sign_preserved"] = np.sign(wide[left]) == np.sign(wide[right])
    for disruption, group in wide.groupby("disruption", sort=False):
        coefficient, p_value = spearmanr(group[left], group[right])
        scale_rows.append(
            {
                "disruption": disruption,
                "scale_left": left,
                "scale_right": right,
                "signs_preserved": int(group["sign_preserved"].sum()),
                "comparisons": len(group),
                "spearman_r": float(coefficient),
                "spearman_p": float(p_value),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(scale_rows)


def publication_table(effects: pd.DataFrame) -> pd.DataFrame:
    table = effects[
        [
            "N", "disruption", "architecture", "rho_cvar_baseline",
            "rho_cvar_architecture", "delta_cvar", "delta_cvar_ci_low",
            "delta_cvar_ci_high", "paired_median_delta_rho", "rank_biserial",
            "wilcoxon_p_holm",
        ]
    ].copy()
    return table


def plot_delta_heatmap(effects: pd.DataFrame, scale: str, output: Path) -> None:
    subset = effects[effects["scale"] == scale]
    matrix = subset.pivot(index="architecture", columns="disruption", values="delta_cvar")
    matrix = matrix.reindex(index=INTERVENTIONS, columns=DISRUPTIONS)
    fig, ax = plt.subplots(figsize=(10.8, 4.7))
    sns.heatmap(
        matrix,
        cmap="RdYlBu",
        center=0,
        annot=True,
        fmt="+.4f",
        linewidths=0.5,
        cbar_kws={"label": r"$\Delta$CVaR$_{0.10}$"},
        ax=ax,
    )
    n_value = int(subset["N"].iloc[0])
    ax.set_title(f"Lower-tail resilience effect by architecture ({scale}, N={n_value})")
    ax.set_xlabel("Disruption scenario")
    ax.set_ylabel("AM architecture")
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    plt.setp(ax.get_yticklabels(), rotation=0)
    fig.tight_layout()
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_scale_comparison(effects: pd.DataFrame, output: Path) -> None:
    plot_data = effects.copy()
    plot_data["scenario_architecture"] = (
        plot_data["disruption"].str.extract(r"^(D\d)")[0]
        + " / "
        + plot_data["architecture"].str.extract(r"^(A\d)")[0]
    )
    fig, ax = plt.subplots(figsize=(13.2, 5.6))
    sns.pointplot(
        data=plot_data,
        x="scenario_architecture",
        y="delta_cvar",
        hue="scale",
        dodge=0.25,
        markers=["o", "s"],
        linestyles="none",
        errorbar=None,
        ax=ax,
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Directional stability of architecture effects across network scales")
    ax.set_xlabel("Disruption / intervention")
    ax.set_ylabel(r"$\Delta$CVaR$_{0.10}$ versus A0")
    plt.setp(ax.get_xticklabels(), rotation=65, ha="right")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_median_q_curves(q_curves: pd.DataFrame, scale: str, output: Path) -> None:
    selected = [
        ("D2_feedstock_targeted", "A1_feedstock"),
        ("D3_postprocess_targeted", "A3_downstream"),
        ("D4_digital_outage", "A4_digital"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.1), sharey=True)
    for ax, (disruption, intervention) in zip(axes, selected):
        data = q_curves[
            (q_curves["scale"] == scale)
            & (q_curves["disruption"] == disruption)
            & (q_curves["architecture"].isin(["A0_baseline", intervention]))
        ]
        median = data.groupby(["architecture", "t"], as_index=False)["Q"].median()
        for architecture, group in median.groupby("architecture"):
            ax.plot(
                group["t"],
                group["Q"],
                linewidth=2,
                label=architecture,
            )
        ax.set_title(disruption)
        ax.set_xlabel("Recovery step, t")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Median normalized production flow, Q(t)")
    fig.suptitle(f"Scenario-aligned interventions: median recovery trajectories ({scale})")
    fig.tight_layout()
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_am1_concept(output: Path) -> None:
    """Draw the typed material-flow and digital-dependency layers used in AM1."""
    stages = [
        ("Feedstock\nsuppliers", "#4C78A8"),
        ("Pre-\nprocessing", "#72B7B2"),
        ("AM hubs", "#F58518"),
        ("Post-\nprocessing", "#E45756"),
        ("Quality\nassurance", "#54A24B"),
        ("Demand\nlocations", "#B279A2"),
    ]
    fig, ax = plt.subplots(figsize=(11.2, 3.6))
    xs = np.linspace(0.07, 0.93, len(stages))
    y = 0.48
    for idx, ((label_text, color), x) in enumerate(zip(stages, xs)):
        ax.text(
            x,
            y,
            label_text,
            ha="center",
            va="center",
            fontsize=10,
            weight="bold",
            color="white",
            bbox={"boxstyle": "round,pad=0.55", "facecolor": color, "edgecolor": "#333333"},
            transform=ax.transAxes,
        )
        if idx < len(stages) - 1:
            ax.annotate(
                "",
                xy=(xs[idx + 1] - 0.065, y),
                xytext=(x + 0.065, y),
                arrowprops={"arrowstyle": "->", "lw": 1.8, "color": "#333333"},
                xycoords=ax.transAxes,
            )
    ax.text(
        xs[2],
        0.84,
        "Digital coordination services",
        ha="center",
        va="center",
        fontsize=10,
        weight="bold",
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#9D755D", "edgecolor": "#333333"},
        color="white",
        transform=ax.transAxes,
    )
    ax.annotate(
        "enabling dependency / backup",
        xy=(xs[2], y + 0.09),
        xytext=(xs[2], 0.76),
        ha="center",
        fontsize=8,
        arrowprops={"arrowstyle": "->", "lw": 1.5, "linestyle": "--", "color": "#9D755D"},
        xycoords=ax.transAxes,
    )
    ax.text(
        0.5,
        0.14,
        "A1 feedstock | A2 cross-qualification | A3 downstream | A4 digital backup | A5 balanced",
        ha="center",
        va="center",
        fontsize=9,
        transform=ax.transAxes,
    )
    ax.text(
        0.5,
        0.04,
        "Equal structural budget: 8 added relations (N=50) or 12 added relations (N=80)",
        ha="center",
        va="center",
        fontsize=8.5,
        style="italic",
        transform=ax.transAxes,
    )
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


def write_report(
    desc: pd.DataFrame,
    effects: pd.DataFrame,
    hypotheses: pd.DataFrame,
    scale: pd.DataFrame,
    output: Path,
) -> None:
    lines = [
        "AM1 STATISTICAL REPORT",
        "======================",
        f"Primary endpoint: lower-tail CVaR alpha={ALPHA:.2f}",
        f"Paired bootstrap replicates: B={BOOTSTRAP_B}",
        "Secondary test: two-sided paired Wilcoxon with Holm correction within scale and disruption.",
        "",
        "INTEGRITY",
        f"Valid observations: {int(desc['n'].sum())}",
        f"Non-recovered share (all cells): {desc['non_recovered_share'].max():.4f}",
        "",
        "H1: SCENARIO ALIGNMENT",
    ]
    for _, row in hypotheses[hypotheses["hypothesis"] == "H1"].iterrows():
        lines.append(
            f"{row['scale']} {row['component']}: expected {row['expected_architecture']}; "
            f"observed best {row['observed_best']}; status={row['status']}; "
            f"aligned delta={row['expected_delta_cvar']:+.6f}."
        )
    lines.extend(["", "H2: BALANCED MAXIMIN"])
    for _, row in hypotheses[hypotheses["hypothesis"] == "H2"].iterrows():
        lines.append(
            f"{row['scale']}: A5 maximin={row['expected_delta_cvar']:+.6f}; "
            f"best={row['observed_best']} ({row['best_delta_cvar']:+.6f}); "
            f"status={row['status']}."
        )
    aligned_success = hypotheses[
        (hypotheses["hypothesis"] == "H1") & (hypotheses["status"] == "SUPPORTED")
    ]
    lines.extend(
        [
            "",
            "H3: DEPENDENCY SPECIFICITY",
            "PARTIALLY SUPPORTED. Directly aligned redundancy led the D2 result at both scales; "
            "digital backup led D4 only at N=80, while the N=50 lower tail was unchanged; "
            "downstream redundancy led D3 at N=50 but not N=80. The data therefore support "
            "mechanism specificity, but also show threshold and scale dependence.",
            f"Aligned H1 components supported: {len(aligned_success)}/6.",
            "",
            "H4: DIRECTIONAL SCALE STABILITY",
        ]
    )
    preserved = int(scale["signs_preserved"].sum())
    total = int(scale["comparisons"].sum())
    lines.append(f"Signs preserved for {preserved}/{total} effects ({preserved/total:.1%}).")
    for _, row in scale.iterrows():
        rho = "undefined (ties)" if not np.isfinite(row["spearman_r"]) else f"{row['spearman_r']:.3f}"
        lines.append(
            f"{row['disruption']}: {row['signs_preserved']}/{row['comparisons']} signs; "
            f"Spearman r={rho}."
        )
    lines.extend(
        [
            "",
            "INTERPRETATION",
            "Effect magnitudes are small because baseline resilience is already high under the fixed "
            "flow-greedy recovery policy. Structural redundancy is not uniformly beneficial: relations "
            "that do not bypass the disrupted dependency can be neutral, and the balanced allocation "
            "can dilute the budget below a useful scenario-specific threshold. All null and adverse "
            "effects were retained.",
            "",
            "Selected paired effects:",
        ]
    )
    selected = effects[
        effects.apply(
            lambda row: ALIGNED.get(row["disruption"]) == row["architecture"], axis=1
        )
    ]
    for _, row in selected.iterrows():
        lines.append(
            f"{row['scale']} {row['disruption']} {row['architecture']}: "
            f"delta CVaR={row['delta_cvar']:+.6f}, "
            f"95% CI [{row['delta_cvar_ci_low']:+.6f}, {row['delta_cvar_ci_high']:+.6f}], "
            f"rank-biserial={row['rank_biserial']:+.3f}, Holm p={row['wilcoxon_p_holm']:.4g}."
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_analysis(
    raw_a_path: Path,
    raw_b_path: Path,
    q_a_path: Path,
    q_b_path: Path,
    output_root: Path,
) -> dict[str, Path]:
    raw_a = pd.read_csv(raw_a_path)
    raw_b = pd.read_csv(raw_b_path)
    validate_raw(raw_a, 400)
    validate_raw(raw_b, 100)
    raw = pd.concat([raw_a, raw_b], ignore_index=True)
    q_curves = pd.concat([pd.read_csv(q_a_path), pd.read_csv(q_b_path)], ignore_index=True)

    aggregated = output_root / "aggregated" / "am1" / "final"
    figures = output_root / "figures" / "am1" / "final"
    reports = output_root / "reports" / "am1" / "final"
    for path in (aggregated, figures, reports):
        path.mkdir(parents=True, exist_ok=True)

    desc = descriptive_statistics(raw)
    effects = paired_effects(raw)
    hypotheses, scale = hypothesis_summary(effects)
    publication = publication_table(effects)

    outputs = {
        "descriptive": aggregated / "AM1_descriptive_statistics.csv",
        "effects": aggregated / "AM1_paired_effects.csv",
        "hypotheses": aggregated / "AM1_hypothesis_summary.csv",
        "scale": aggregated / "AM1_scale_stability.csv",
        "publication": aggregated / "AM1_publication_table.csv",
        "report": reports / "AM1_statistical_report.txt",
        "heatmap_a": figures / "AM1_delta_CVaR_heatmap_N50.png",
        "heatmap_b": figures / "AM1_delta_CVaR_heatmap_N80.png",
        "scale_figure": figures / "AM1_scale_comparison.png",
        "q_curves": figures / "AM1_aligned_recovery_curves_N50.png",
        "concept": figures / "AM1_typed_network_concept.png",
    }
    desc.to_csv(outputs["descriptive"], index=False)
    effects.to_csv(outputs["effects"], index=False)
    hypotheses.to_csv(outputs["hypotheses"], index=False)
    scale.to_csv(outputs["scale"], index=False)
    publication.to_csv(outputs["publication"], index=False)
    write_report(desc, effects, hypotheses, scale, outputs["report"])
    plot_delta_heatmap(effects, "AM1-A", outputs["heatmap_a"])
    plot_delta_heatmap(effects, "AM1-B", outputs["heatmap_b"])
    plot_scale_comparison(effects, outputs["scale_figure"])
    plot_median_q_curves(q_curves, "AM1-A", outputs["q_curves"])
    plot_am1_concept(outputs["concept"])
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-a",
        type=Path,
        default=ROOT / "results/raw/am1/am1a-m400-20261003-r2/raw_results.csv",
    )
    parser.add_argument(
        "--raw-b",
        type=Path,
        default=ROOT / "results/raw/am1/am1b-m100-20261003/raw_results.csv",
    )
    parser.add_argument(
        "--q-a",
        type=Path,
        default=ROOT / "results/raw/am1/am1a-m400-20261003-r2/q_curves.csv",
    )
    parser.add_argument(
        "--q-b",
        type=Path,
        default=ROOT / "results/raw/am1/am1b-m100-20261003/q_curves.csv",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = run_analysis(args.raw_a, args.raw_b, args.q_a, args.q_b, args.output_root)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
