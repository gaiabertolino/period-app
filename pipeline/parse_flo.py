#!/usr/bin/env python3
"""Convert a Flo data export (JSON or TXT) into the canonical cycle CSV.

Flo has no self-service CSV export: you ask support (in-app chat) for your
data and receive JSON or TXT. The format isn't documented and changes over
time, so this parser is deliberately tolerant:

* JSON: walks the whole document and collects dates from keys that look like
  period/cycle starts (e.g. "period_start_date", "startDate", "start"), inside
  objects that look like periods or cycles. If none are found it falls back to
  every date-like value under a key containing "period" or "cycle".
* TXT: collects every date it can recognise (YYYY-MM-DD, YYYY/MM/DD,
  DD.MM.YYYY; use --dayfirst / --monthfirst for DD/MM/YYYY vs MM/DD/YYYY).

If the export lists every bleeding day rather than only start days, consecutive
days are collapsed: a date starts a new period when it comes more than
--gap days (default 10) after the previous date.

ALWAYS check the output (pipeline/validate_csv.py) and compare a few dates with
the app. Adjust START_KEYS once you have a real export.

Usage:
    python pipeline/parse_flo.py flo_export.json -o data/private/cycles.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

START_KEYS = {
    "period_start_date", "periodstartdate", "start_date", "startdate", "start",
    "cycle_start_date", "cyclestartdate", "period_start", "periodstart", "date_start",
}
CONTAINER_HINTS = ("period", "cycle", "menstruation", "bleeding")

_ISO = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?\b")
_DOTTED = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
_SLASHED = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def dates_in_text(text: str, dayfirst: bool | None = None) -> list[date]:
    out: list[date] = []
    for m in _ISO.finditer(text):
        dt = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            out.append(dt)
    for m in _DOTTED.finditer(text):
        dt = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if dt:
            out.append(dt)
    for m in _SLASHED.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if dayfirst is None:
            if a > 12:
                dayfirst_here = True
            elif b > 12:
                dayfirst_here = False
            else:
                continue  # ambiguous: skip unless the user says which
        else:
            dayfirst_here = dayfirst
        dt = _safe_date(y, b, a) if dayfirst_here else _safe_date(y, a, b)
        if dt:
            out.append(dt)
    return out


def _value_to_date(value) -> date | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # epoch seconds or milliseconds
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(ts, timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        found = dates_in_text(value)
        return found[0] if found else None
    return None


def dates_in_json(doc) -> list[date]:
    starts: list[date] = []
    loose: list[date] = []

    def walk(node, path: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                k = str(key).lower()
                norm = k.replace("-", "_")
                in_container = any(h in p for p in path + (k,) for h in CONTAINER_HINTS)
                if norm in START_KEYS or norm.replace("_", "") in START_KEYS:
                    dt = _value_to_date(value)
                    if dt and (in_container or "period" in k or "cycle" in k):
                        starts.append(dt)
                        continue
                if in_container and not isinstance(value, (dict, list)):
                    dt = _value_to_date(value)
                    if dt and ("end" not in k):
                        loose.append(dt)
                walk(value, path + (k,))
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(doc, ())
    return starts or loose


def collapse_to_starts(dates: list[date], gap: int) -> list[date]:
    starts: list[date] = []
    prev: date | None = None
    for d in sorted(set(dates)):
        if prev is None or (d - prev).days > gap:
            starts.append(d)
        prev = d
    return starts


_FLO_LINE = re.compile(r"^Period (start|end) date:\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})", re.M)


def parse_flo_report(text: str, offset_hours: int | None = None) -> tuple[list[tuple[date, date | None]], int]:
    """Flo's TXT report: blocks of "Period start date: 2013-11-08 23:00:00.0" /
    "Period end date: ...". Other sections of the file (sleep, sport, ...) are ignored.

    Flo stores local midnight as a UTC timestamp, so in UTC+1 a period that
    started on 9 Nov appears as "2013-11-08 23:00". The offset is guessed from
    the most common hour (23:00 -> +1h, 22:00 -> +2h, 00:00 -> 0) unless given,
    then added to every timestamp before taking the date.
    Returns ([(start, end)], offset_hours).
    """
    entries = [(kind, ymd, int(hh), int(mm)) for kind, ymd, hh, mm in _FLO_LINE.findall(text)]
    if offset_hours is None:
        hours = [h for kind, _, h, _ in entries if kind == "start"]
        common = max(set(hours), key=hours.count) if hours else 0
        offset_hours = 24 - common if common >= 12 else -common

    def to_date(ymd: str, hh: int, mm: int) -> date:
        dt = datetime.fromisoformat(f"{ymd}T{hh:02d}:{mm:02d}") + timedelta(hours=offset_hours)
        return dt.date()

    periods: list[tuple[date, date | None]] = []
    for kind, ymd, hh, mm in entries:
        if kind == "start":
            periods.append((to_date(ymd, hh, mm), None))
        elif periods and periods[-1][1] is None:
            periods[-1] = (periods[-1][0], to_date(ymd, hh, mm))
    return periods, offset_hours


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Flo export (JSON/TXT) -> canonical cycle CSV.")
    p.add_argument("export", help="Flo export file (.json or .txt)")
    p.add_argument("-o", "--output", help="output CSV (default: stdout)")
    p.add_argument("--gap", type=int, default=10,
                   help="days without a logged date that separate two periods (default 10)")
    order = p.add_mutually_exclusive_group()
    order.add_argument("--dayfirst", action="store_true", help="read NN/NN/YYYY as DD/MM/YYYY")
    order.add_argument("--monthfirst", action="store_true", help="read NN/NN/YYYY as MM/DD/YYYY")
    p.add_argument("--offset-hours", type=int, default=None,
                   help="TXT report: hours to add to Flo's timestamps (default: guessed)")
    args = p.parse_args(argv)

    text = Path(args.export).read_text(encoding="utf-8-sig", errors="replace")
    dayfirst = True if args.dayfirst else False if args.monthfirst else None

    if _FLO_LINE.search(text):
        periods, offset = parse_flo_report(text, args.offset_hours)
        by_start: dict[date, date | None] = {}
        for start, end in periods:
            by_start.setdefault(start, end)
        out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
        try:
            w = csv.writer(out, lineterminator="\n")
            w.writerow(["cycle_start_date", "period_length"])
            for start in sorted(by_start):
                end = by_start[start]
                w.writerow([start.isoformat(), (end - start).days + 1 if end and end >= start else ""])
        finally:
            if args.output:
                out.close()
        starts = sorted(by_start)
        print(f"Parsed {args.export} as a Flo TXT report: {len(periods)} periods -> {len(starts)} unique starts "
              f"({starts[0]} to {starts[-1]}), timestamps shifted by {offset:+d}h. "
              f"Check the result with validate_csv.py.", file=sys.stderr)
        return 0

    try:
        dates = dates_in_json(json.loads(text))
        source = "JSON"
    except json.JSONDecodeError:
        dates = dates_in_text(text, dayfirst)
        source = "text"

    starts = collapse_to_starts(dates, args.gap)
    if not starts:
        print(f"No dates found in {args.export} (parsed as {source}).", file=sys.stderr)
        return 1

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["cycle_start_date"])
        for d in starts:
            w.writerow([d.isoformat()])
    finally:
        if args.output:
            out.close()
    print(f"Parsed {args.export} as {source}: {len(dates)} dates -> {len(starts)} period starts "
          f"({starts[0]} to {starts[-1]}). Check the result with validate_csv.py.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
