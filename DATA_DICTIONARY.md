# AM1 data dictionary

## Raw run-level files

`data/raw/*/raw_results.csv` contains one row for each architecture–disruption–paired-network simulation.

| Field | Meaning |
|---|---|
| `series`, `plan`, `scale`, `N` | Experiment, execution plan, network scale, and number of typed nodes. |
| `architecture` | `A0_baseline` or one of five equal-budget AM interventions (`A1`–`A5`). |
| `disruption` | One of five AM-specific disruption scenarios (`D1`–`D5`). |
| `paired_run_id`, `run_idx` | Pairing identifier and within-scenario Monte Carlo index. |
| `network_seed`, `graph_seed`, `capacity_seed` | Deterministic seeds controlling the shared base network and capacities. |
| `disruption_seed`, `recovery_seed` | Deterministic seeds controlling damage and any recovery-policy randomness. |
| `seed_policy` | Description of the pairing convention. |
| `intervention_budget`, `applied_budget` | Allowed and actually added architecture relations. The baseline adds zero. |
| `n_*` | Counts of each AM role in the typed network. |
| `recovery_strategy`, `mu`, `T_max` | Recovery rule, repair actions per step, and simulation horizon. |
| `F0` | Undisrupted maximum material flow. |
| `rho` | Mean normalized flow over the full trajectory. |
| `robustness` | Minimum normalized flow after disruption. |
| `final_recovery` | Final normalized flow at `T_max`. |
| `t95` | First recovery step reaching 95% of baseline flow. |
| `non_recovered` | Boolean indicator that the 95% target was not reached. |
| `physical_failures` | Count of directly damaged physical elements. |
| `blocked_hubs` | Count of AM hubs disabled by a digital dependency outage. |
| `functionally_lost_nodes` | Total directly or functionally unavailable nodes. |
| `repaired_elements` | Number of repaired elements during the trajectory. |
| `selected_disruption_target` | Target node(s) or failed element list, serialized as text. |
| `valid`, `exclusion_reason` | Run-validity flag and reason for any exclusion. |
| `runtime_seconds` | Wall-clock runtime of the individual simulation. |
| `git_commit`, `git_dirty`, `config_hash` | Exact code and configuration provenance. |

## Raw trajectory files

`data/raw/*/q_curves.csv` contains one row per time step.

| Field | Meaning |
|---|---|
| `series`, `plan`, `scale` | Experiment identifiers. |
| `architecture`, `disruption`, `paired_run_id` | Paired scenario identifiers. |
| `t` | Discrete time step, from 0 through 50. |
| `Q` | Maximum material flow normalized by the undisrupted baseline. |

## Aggregated files

- `AM1_descriptive_statistics.csv`: distributional summaries by scale, architecture, and disruption.
- `AM1_paired_effects.csv`: paired intervention-versus-baseline effects, lower-tail differences, confidence intervals, Wilcoxon tests, Holm-adjusted probabilities, and rank-biserial effects.
- `AM1_hypothesis_summary.csv`: preregistered hypothesis outcomes.
- `AM1_scale_stability.csv`: sign stability across `N=50` and `N=80`.
- `AM1_publication_table.csv`: compact values used in the manuscript.

The exact statistical definitions and grouping logic are implemented in `code/src/am1/analysis.py`.
