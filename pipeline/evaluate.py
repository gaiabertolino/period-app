#!/usr/bin/env python3
"""Expanding-window backtest of the cycle model.

For each logged start i (after the first --min-history dates), predict it from
starts 1..i-1 only, then compare with what actually happened. Reports:

* MAE in days of the point prediction (and bias, median, max error);
* empirical coverage of the credible intervals: an 80% interval should contain
  the real date about 80% of the time;
* the same MAE for a naive "previous start + 28 days" baseline.

Targets whose real gap is outside the hygiene thresholds are skipped (they are
treated as logging errors, the same way the model treats them).

Usage:
    python pipeline/evaluate.py data/sample_synthetic.csv [--levels 0.5,0.8,0.95] [--json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys

from fit_model import add_common_args, iso_to_day, predict, prior_from_args, read_dates


def backtest(dates: list[str], levels: list[float], min_history: int, min_length: float,
             max_length: float, prior: dict) -> dict:
    days = sorted({iso_to_day(d) for d in dates})
    iso = sorted(set(dates))
    errors: list[int] = []
    baseline: list[int] = []
    covered = {lvl: 0 for lvl in levels}
    widths = {lvl: [] for lvl in levels}
    skipped = 0

    for i in range(max(1, min_history), len(days)):
        actual = days[i]
        gap = actual - days[i - 1]
        if not (min_length <= gap <= max_length):
            skipped += 1
            continue
        history = iso[:i]
        point = None
        for lvl in levels:
            r = predict(history, level=lvl, min_length=min_length, max_length=max_length,
                        n_predicted=1, prior=prior)
            lo, hi = iso_to_day(r["lo_date"]), iso_to_day(r["hi_date"])
            covered[lvl] += int(lo <= actual <= hi)
            widths[lvl].append(hi - lo)
            point = iso_to_day(r["next_date"])
        errors.append(actual - point)
        baseline.append(actual - (days[i - 1] + 28))

    n = len(errors)
    if n == 0:
        return {"n_predictions": 0, "skipped": skipped}
    abs_err = [abs(e) for e in errors]
    return {
        "n_predictions": n,
        "skipped": skipped,
        "mae_days": statistics.fmean(abs_err),
        "median_abs_error_days": statistics.median(abs_err),
        "max_abs_error_days": max(abs_err),
        "bias_days": statistics.fmean(errors),
        "baseline_28d_mae_days": statistics.fmean(abs(e) for e in baseline),
        "coverage": {f"{lvl:g}": covered[lvl] / n for lvl in levels},
        "mean_interval_width_days": {f"{lvl:g}": statistics.fmean(widths[lvl]) for lvl in levels},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Expanding-window backtest (MAE + interval coverage).")
    p.add_argument("csv")
    p.add_argument("--levels", default="0.5,0.8,0.95", help="comma-separated credible levels")
    p.add_argument("--min-history", type=int, default=2,
                   help="number of logged dates before the first evaluated prediction (default 2)")
    p.add_argument("--json", action="store_true", help="print JSON only")
    add_common_args(p)
    args = p.parse_args(argv)

    levels = [float(x) for x in args.levels.split(",") if x.strip()]
    res = backtest(read_dates(args.csv), levels, args.min_history, args.min_length,
                   args.max_length, prior_from_args(args))
    if args.json:
        json.dump(res, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"Backtest on {args.csv}")
    if res["n_predictions"] == 0:
        print("  not enough data to evaluate")
        return 0
    print(f"  predictions evaluated : {res['n_predictions']} (skipped {res['skipped']} outlier gaps)")
    print(f"  MAE                   : {res['mae_days']:.2f} days "
          f"(median {res['median_abs_error_days']:.1f}, max {res['max_abs_error_days']})")
    print(f"  bias (actual - pred)  : {res['bias_days']:+.2f} days")
    print(f"  baseline +28d MAE     : {res['baseline_28d_mae_days']:.2f} days")
    for lvl in levels:
        key = f"{lvl:g}"
        print(f"  {lvl:.0%} interval        : coverage {res['coverage'][key]:.1%}, "
              f"mean width {res['mean_interval_width_days'][key]:.1f} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
