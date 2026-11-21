#!/usr/bin/env python3
"""Check a cycle CSV against the canonical schema.

Errors (exit code 1): missing `cycle_start_date` header, invalid dates,
duplicate dates. Warnings (exit code 0): rows not sorted, cycle lengths outside
the hygiene thresholds (default 15-90 days), which the model leaves out.

Usage:
    python pipeline/validate_csv.py data/sample_synthetic.csv [--min-length 15 --max-length 90]
"""
from __future__ import annotations

import argparse
import csv
import sys

from fit_model import DATE_COLUMN, DEFAULT_MAX_LENGTH, DEFAULT_MIN_LENGTH, day_to_iso, iso_to_day


def validate(path: str, min_length: float, max_length: float) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return ["file is empty"], warnings, 0
        cols = [h.strip().lower() for h in header]
        if DATE_COLUMN not in cols:
            return [f"missing required header '{DATE_COLUMN}' (found: {header})"], warnings, 0
        idx = cols.index(DATE_COLUMN)

        seen: dict[int, int] = {}
        order: list[int] = []
        for line, row in enumerate(reader, start=2):
            if not any(field.strip() for field in row):
                continue
            value = row[idx].strip() if idx < len(row) else ""
            day = iso_to_day(value)
            if day is None:
                errors.append(f"line {line}: invalid date {value!r} (expected YYYY-MM-DD)")
                continue
            if day in seen:
                errors.append(f"line {line}: duplicate date {value} (first seen on line {seen[day]})")
                continue
            seen[day] = line
            order.append(day)

    if order != sorted(order):
        warnings.append("rows are not sorted by date (they will be sorted on import)")
    days = sorted(order)
    for a, b in zip(days, days[1:]):
        length = b - a
        if not (min_length <= length <= max_length):
            warnings.append(f"cycle {day_to_iso(a)} -> {day_to_iso(b)} is {length} days, "
                            f"outside {min_length:g}-{max_length:g}: excluded from the model")
    return errors, warnings, len(days)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate a canonical cycle CSV.")
    p.add_argument("csv")
    p.add_argument("--min-length", type=float, default=DEFAULT_MIN_LENGTH)
    p.add_argument("--max-length", type=float, default=DEFAULT_MAX_LENGTH)
    args = p.parse_args(argv)

    errors, warnings, n = validate(args.csv, args.min_length, args.max_length)
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"{args.csv}: {n} valid dates, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
