"""Окрема CLI-точка входу для захищеної експериментальної серії AM1."""

from __future__ import annotations

import argparse
import sys

from src.am1.runner import load_am1_config, resolve_plan, run_am1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="am1_main.py",
        description="Запуск ізольованої AM1-серії без зміни попередніх результатів.",
    )
    parser.add_argument(
        "--plan",
        choices=("smoke", "calibration", "am1a", "am1b"),
        default="smoke",
        help="План запуску; до окремого підтвердження використовуйте smoke.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Опційне перевизначення M для контрольного запуску.",
    )
    parser.add_argument(
        "--output-root",
        default="results",
        help="Корінь outputs; AM1 автоматично пише лише у */am1/<run-label>.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Нова унікальна назва output namespace.",
    )
    parser.add_argument(
        "--config",
        default="config/series_AM1.yaml",
        help="Шлях до AM1 YAML-конфігурації.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        config = load_am1_config(args.config)
        plan = resolve_plan(config, args.plan, runs_override=args.runs)
        outputs = run_am1(
            config,
            plan,
            output_root=args.output_root,
            run_label=args.run_label,
        )
        if plan.name == "calibration":
            from src.am1.calibration import write_calibration_report

            report_outputs = write_calibration_report(
                raw_path=outputs["raw_results"],
                q_path=outputs["q_curves"],
                report_dir=outputs["metadata"].parent,
                architectures=plan.architectures,
                disruptions=plan.disruptions,
                n_runs=plan.n_runs,
                T_max=int(config["simulation"]["T_max"]),
                target=float(config["simulation"]["Q_target_frac"]),
                alpha=float(config["metrics"]["alpha_cvar"]),
            )
            outputs.update(report_outputs)
    except (FileNotFoundError, FileExistsError, KeyError, TypeError, ValueError) as exc:
        print(f"Помилка AM1: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(
        f"AM1 {plan.name} завершено: M={plan.n_runs}, N={plan.N}, "
        f"комбінацій={len(plan.architectures) * len(plan.disruptions)}."
    )
    for name, path in outputs.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
