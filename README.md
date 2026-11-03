# AM1 reproducibility package v1.0.1

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23931297.svg)](https://doi.org/10.5281/zenodo.23931297)

This archive accompanies the revised manuscript **“Resilience-Oriented Design of Distributed Additive Manufacturing Networks”** by Stanislav V. Pohorielov and Oleksii V. Yanovskyi.

Version 1.0.1 is a metadata-only successor to version 1.0.0, published after enabling Zenodo preservation. The scientific payload, code, configuration and simulation results are unchanged.

It contains the isolated AM1 simulation code, fixed configuration, deterministic seed policy, complete raw outputs for 15,000 simulations, aggregated tables, statistical report, and publication figures. No outputs from the authors' earlier experimental series are included or modified.

## Study design

AM1 is a paired Monte Carlo experiment on typed distributed additive-manufacturing networks.

- AM1-A: `N=50`, 400 paired base networks, six architectures, five disruptions, 12,000 runs.
- AM1-B: `N=80`, 100 paired base networks, six architectures, five disruptions, 3,000 runs.
- Recovery: fixed flow-greedy policy, one repair action per time step (`mu=1`).
- Horizon: `T_max=50`; recovery target: `Q(t) >= 0.95`.
- Lower-tail measure: CVaR of the lowest 10% of integral-resilience values.
- Production commit recorded in every run: `89ab5aeb08b35e1283f5d3cd5694ced295c4ee06`.
- Configuration hash recorded in every run: `c9b9f3555713dbe83b841fab6d868c487ab251215bf413ba08cccd9f5e29b4f8`.

The exact model, interventions, disruptions, hypotheses, pairing policy, and protected output namespaces are defined in `protocol/Protocol_AM1_distributed_additive_manufacturing.md`.

## Directory map

```text
code/                    isolated AM1 runner, analysis, shared flow/metric modules, tests
config/                  fixed YAML configuration used by the production runs
protocol/                preregistered experimental protocol
data/raw/AM1-A_N50/      12,000 run-level rows and 612,000 Q(t) rows
data/raw/AM1-B_N80/      3,000 run-level rows and 153,000 Q(t) rows
data/aggregated/          descriptive, paired-effect, hypothesis, scale, publication tables
figures/                 figures generated from the included raw data
reports/run_metadata/    immutable metadata for both production runs
reports/final/           statistical report and overlap audit
DATA_DICTIONARY.md       definitions of the main data fields
MANIFEST.sha256          SHA-256 checksum for every payload file in this release
```

## Software environment

The production simulation was executed on Apple Silicon under macOS. The code requires Python 3.10 or later and the packages listed in `requirements-am1.txt`. The release was independently smoke-tested using Python 3.13.5.

Create an isolated environment and install the requirements:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-am1.txt
```

All commands below should be run from the root of the extracted archive.

## Verify the archive

```bash
shasum -a 256 -c MANIFEST.sha256
PYTHONPATH=code pytest -q code/tests/am1
```

## Run a deterministic smoke experiment

The smoke command writes only to a new AM1 namespace under the chosen temporary output root. It never overwrites an existing namespace.

```bash
PYTHONPATH=code python code/am1_main.py \
  --config config/series_AM1.yaml \
  --plan smoke \
  --output-root /tmp/am1-smoke \
  --run-label verification-smoke
```

## Reproduce the full simulation

Use new, empty output roots because the runner refuses to overwrite raw results.

```bash
PYTHONPATH=code python code/am1_main.py \
  --config config/series_AM1.yaml \
  --plan am1a \
  --output-root /tmp/am1-reproduction \
  --run-label am1a-reproduction

PYTHONPATH=code python code/am1_main.py \
  --config config/series_AM1.yaml \
  --plan am1b \
  --output-root /tmp/am1-reproduction \
  --run-label am1b-reproduction
```

Floating-point runtimes can vary by hardware; the deterministic seeds, architecture/disruption pairing, row counts, metrics, and configuration identity should remain reproducible.

## Regenerate the statistics and figures from the included raw data

```bash
PYTHONPATH=code python -m src.am1.analysis \
  --raw-a data/raw/AM1-A_N50/raw_results.csv \
  --raw-b data/raw/AM1-B_N80/raw_results.csv \
  --q-a data/raw/AM1-A_N50/q_curves.csv \
  --q-b data/raw/AM1-B_N80/q_curves.csv \
  --output-root /tmp/am1-analysis
```

The regenerated CSV tables and PNG figures will appear under `/tmp/am1-analysis`.

## Data integrity and provenance

Both run metadata files report `git_dirty=false`; therefore, the production outputs were created from the committed code identified above. Every raw row also stores the production commit and configuration hash. `MANIFEST.sha256` verifies transport-level integrity of every payload file; the manifest itself is necessarily excluded.

## Citation and license note

Suggested citation metadata are supplied in `CITATION.cff`. The version-specific archived release is available at [https://doi.org/10.5281/zenodo.23931297](https://doi.org/10.5281/zenodo.23931297); the concept DOI for all versions is [https://doi.org/10.5281/zenodo.23931296](https://doi.org/10.5281/zenodo.23931296).

Copyright © 2026 Stanislav V. Pohorielov and Oleksii V. Yanovskyi. All rights reserved. The materials may be used for verification and peer review. Any further reuse, redistribution, modification, or commercial use requires prior written permission from the authors.

## Contact

Stanislav V. Pohorielov, National Technical University “Kharkiv Polytechnic Institute”.

