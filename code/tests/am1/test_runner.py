"""Тести paired AM1 runner і захищених output namespaces."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.am1.runner import load_am1_config, resolve_plan, run_am1


CONFIG_PATH = Path("config/series_AM1.yaml")


def test_smoke_plan_matches_preregistered_canonical_combination() -> None:
    config = load_am1_config(CONFIG_PATH)
    plan = resolve_plan(config, "smoke")

    assert plan.N == 50
    assert plan.n_runs == 5
    assert plan.seed_start == 910000
    assert plan.architectures == ("A5_balanced",)
    assert plan.disruptions == ("D4_digital_outage",)


def test_invalid_runs_override_is_rejected() -> None:
    config = load_am1_config(CONFIG_PATH)
    with pytest.raises(ValueError, match="додатним"):
        resolve_plan(config, "smoke", runs_override=0)


def test_smoke_is_deterministic_and_writes_only_am1_namespace(tmp_path: Path) -> None:
    config = load_am1_config(CONFIG_PATH)
    plan = resolve_plan(config, "smoke")
    first = run_am1(config, plan, tmp_path / "first", run_label="smoke-a")
    second = run_am1(config, plan, tmp_path / "second", run_label="smoke-b")

    raw_first = pd.read_csv(first["raw_results"])
    raw_second = pd.read_csv(second["raw_results"])
    q_first = pd.read_csv(first["q_curves"])
    q_second = pd.read_csv(second["q_curves"])

    assert len(raw_first) == 5
    assert raw_first["valid"].all()
    assert raw_first["paired_run_id"].is_unique
    assert raw_first["repaired_elements"].gt(0).all()
    assert raw_first["n_am_hubs"].eq(20).all()
    assert raw_first["n_digital_services"].eq(2).all()
    assert len(q_first) == 5 * 51
    assert q_first.groupby("paired_run_id").size().eq(51).all()

    stable_columns = [
        column
        for column in raw_first.columns
        if column not in {"runtime_seconds", "git_commit"}
    ]
    pd.testing.assert_frame_equal(
        raw_first[stable_columns],
        raw_second[stable_columns],
        check_exact=True,
    )
    pd.testing.assert_frame_equal(q_first, q_second, check_exact=True)

    for path in first.values():
        assert "/am1/" in path.as_posix()
    metadata = json.loads(first["metadata"].read_text(encoding="utf-8"))
    assert metadata["n_raw_rows"] == 5
    assert metadata["n_q_rows"] == 255


def test_existing_namespace_is_never_overwritten(tmp_path: Path) -> None:
    config = load_am1_config(CONFIG_PATH)
    plan = resolve_plan(config, "smoke", runs_override=1)
    run_am1(config, plan, tmp_path, run_label="immutable")

    with pytest.raises(FileExistsError, match="не переписуються"):
        run_am1(config, plan, tmp_path, run_label="immutable")
