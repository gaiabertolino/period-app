#!/usr/bin/env python3
"""Generate data/sample_synthetic.csv (fixed seed, fake data, no real person).

About 40 cycles of ~28.5 +/- 2.5 days with a slow drift, plus two deliberate
data problems so the hygiene rules have something to flag:
  * a mistaken extra entry 9 days after a real start (a 9-day "cycle");
  * a 3-month gap with no logs (a ~95-day "cycle").
A `notes` column shows that extra columns survive import/export.
"""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_synthetic.csv"


def main() -> int:
    rng = random.Random(20240501)
    d = date(2022, 1, 10)
    rows = [(d, "")]
    for i in range(40):
        mean = 28.5 + 0.03 * i
        length = max(21, min(38, round(rng.gauss(mean, 2.5))))
        if i == 14:
            rows.append((d + timedelta(days=9), "logged by mistake"))
        if i == 27:
            length = 95
            note = "no logs for a while"
        else:
            note = ""
        d = d + timedelta(days=length)
        rows.append((d, note))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["cycle_start_date", "notes"])
        for day, note in sorted(rows):
            w.writerow([day.isoformat(), note])
    print(f"wrote {OUT} ({len(rows)} dates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
