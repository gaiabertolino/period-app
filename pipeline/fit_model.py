#!/usr/bin/env python3
"""Fit the cycle-length model to a canonical CSV and print the prediction.

Same computation as app/js/model.js, line for line (tests/test_parity.py checks
this). Pure standard library, no numpy/scipy, so results match the browser.

Usage:
    python pipeline/fit_model.py data/sample_synthetic.csv [--level 0.8]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import date, timedelta

DEFAULT_PRIOR = {"mu0": 28.0, "kappa0": 1.0, "alpha0": 2.0, "beta0": 16.0}
DEFAULT_LEVEL = 0.8
DEFAULT_MIN_LENGTH = 15
DEFAULT_MAX_LENGTH = 90
DEFAULT_N_PREDICTED = 12
NORMAL_FALLBACK_NU = 1000
DATE_COLUMN = "cycle_start_date"

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_EPOCH = date(1970, 1, 1)


# ---------- dates ----------

def iso_to_day(iso: str) -> int | None:
    """Days since 1970-01-01, or None if not a valid YYYY-MM-DD date."""
    m = _ISO_RE.match(str(iso).strip())
    if not m:
        return None
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    if d.year < 1000:
        return None
    return (d - _EPOCH).days


def day_to_iso(day: int) -> str:
    return (_EPOCH + timedelta(days=day)).isoformat()


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


# ---------- special functions ----------

_LANCZOS = [
    0.99999999999980993, 676.5203681218851, -1259.1392167224028,
    771.32342877765313, -176.61502916214059, 12.507343278686905,
    -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
]


def lgamma(x: float) -> float:
    # Same Lanczos approximation as model.js (not math.lgamma) for parity.
    if x < 0.5:
        return math.log(math.pi / abs(math.sin(math.pi * x))) - lgamma(1 - x)
    x -= 1
    a = _LANCZOS[0]
    t = x + 7.5
    for i in range(1, 9):
        a += _LANCZOS[i] / (x + i)
    return 0.5 * math.log(2 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(a)


def _betacf(a: float, b: float, x: float) -> float:
    maxit, eps, fpmin = 300, 1e-15, 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, nu: float) -> float:
    x = nu / (nu + t * t)
    tail = 0.5 * betainc(nu / 2, 0.5, x)
    return 1 - tail if t > 0 else tail


_NA = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
       1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
_NB = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
       6.680131188771972e+01, -1.328068155288572e+01]
_NC = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
       -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
_ND = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
       3.754408661907416e+00]


def norm_quantile(p: float) -> float:
    """Acklam's approximation of the standard normal quantile."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return ((((((_NC[0] * q + _NC[1]) * q + _NC[2]) * q + _NC[3]) * q + _NC[4]) * q + _NC[5])
                / ((((_ND[0] * q + _ND[1]) * q + _ND[2]) * q + _ND[3]) * q + 1))
    if p <= 1 - plow:
        q = p - 0.5
        r = q * q
        return (((((((_NA[0] * r + _NA[1]) * r + _NA[2]) * r + _NA[3]) * r + _NA[4]) * r + _NA[5]) * q)
                / (((((_NB[0] * r + _NB[1]) * r + _NB[2]) * r + _NB[3]) * r + _NB[4]) * r + 1))
    q = math.sqrt(-2 * math.log(1 - p))
    return -((((((_NC[0] * q + _NC[1]) * q + _NC[2]) * q + _NC[3]) * q + _NC[4]) * q + _NC[5])
             / ((((_ND[0] * q + _ND[1]) * q + _ND[2]) * q + _ND[3]) * q + 1))


def t_quantile(p: float, nu: float) -> float:
    """Student-t quantile by bisection on the exact CDF (as in model.js)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    if nu >= NORMAL_FALLBACK_NU:
        return norm_quantile(p)
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_quantile(1 - p, nu)
    lo, hi = 0.0, 1.0
    while t_cdf(hi, nu) < p:
        lo = hi
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, nu) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2


# ---------- model ----------

def cycle_lengths(days: list[int], min_length: float, max_length: float) -> list[dict]:
    out = []
    for i in range(1, len(days)):
        length = days[i] - days[i - 1]
        out.append({"from": days[i - 1], "to": days[i], "length": length,
                    "included": min_length <= length <= max_length})
    return out


def fit_nig(lengths: list[float], prior: dict = DEFAULT_PRIOR) -> dict:
    mu0, kappa0, alpha0, beta0 = prior["mu0"], prior["kappa0"], prior["alpha0"], prior["beta0"]
    m = len(lengths)
    if m == 0:
        return {"m": 0, "mean": None, "S": 0.0, "kappa_n": kappa0, "mu_n": mu0,
                "alpha_n": alpha0, "beta_n": beta0}
    total = 0.0
    for x in lengths:
        total += x
    mean = total / m
    s = 0.0
    for x in lengths:
        s += (x - mean) * (x - mean)
    kappa_n = kappa0 + m
    mu_n = (kappa0 * mu0 + m * mean) / kappa_n
    alpha_n = alpha0 + m / 2
    beta_n = beta0 + 0.5 * s + (kappa0 * m * (mean - mu0) * (mean - mu0)) / (2 * kappa_n)
    return {"m": m, "mean": mean, "S": s, "kappa_n": kappa_n, "mu_n": mu_n,
            "alpha_n": alpha_n, "beta_n": beta_n}


def predictive(post: dict) -> dict:
    return {
        "nu": 2 * post["alpha_n"],
        "loc": post["mu_n"],
        "scale": math.sqrt(post["beta_n"] * (post["kappa_n"] + 1) / (post["alpha_n"] * post["kappa_n"])),
    }


def predict(iso_dates: list[str], level: float = DEFAULT_LEVEL, min_length: float = DEFAULT_MIN_LENGTH,
            max_length: float = DEFAULT_MAX_LENGTH, n_predicted: int = DEFAULT_N_PREDICTED,
            prior: dict | None = None) -> dict:
    prior = {**DEFAULT_PRIOR, **(prior or {})}
    days = sorted({d for d in (iso_to_day(s) for s in iso_dates) if d is not None})
    n = len(days)

    lengths = cycle_lengths(days, min_length, max_length)
    post = fit_nig([l["length"] for l in lengths if l["included"]], prior)
    pred = predictive(post)
    q = t_quantile((1 + level) / 2, pred["nu"])
    lo_len = post["mu_n"] - q * pred["scale"]
    hi_len = post["mu_n"] + q * pred["scale"]

    result = {
        "n_dates": n,
        **post,
        "nu": pred["nu"],
        "scale": pred["scale"],
        "q": q,
        "level": level,
        "lo_len": lo_len,
        "hi_len": hi_len,
        "sigma": math.sqrt(post["beta_n"] / (post["alpha_n"] - 1)) if post["alpha_n"] > 1 else None,
        "prior_only": post["m"] == 0,
        "lengths": [{"from": day_to_iso(l["from"]), "to": day_to_iso(l["to"]), "length": l["length"],
                     "included": l["included"]} for l in lengths],
        "n_excluded": sum(1 for l in lengths if not l["included"]),
        "last_date": None,
        "next_date": None,
        "lo_date": None,
        "hi_date": None,
        "upcoming": [],
    }
    if n > 0:
        last = days[-1]
        result["last_date"] = day_to_iso(last)
        result["next_date"] = day_to_iso(last + round_half_up(post["mu_n"]))
        result["lo_date"] = day_to_iso(last + max(1, round_half_up(lo_len)))
        result["hi_date"] = day_to_iso(last + max(1, round_half_up(hi_len)))
        result["upcoming"] = [day_to_iso(last + round_half_up(k * post["mu_n"]))
                              for k in range(1, n_predicted + 1)]
    return result


# ---------- I/O ----------

def read_dates(path: str) -> list[str]:
    """Valid, de-duplicated start dates from a canonical CSV (invalid rows skipped)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = {(h or "").strip().lower(): h for h in (reader.fieldnames or [])}
        if DATE_COLUMN not in fields:
            raise SystemExit(f"{path}: missing required header '{DATE_COLUMN}'")
        col = fields[DATE_COLUMN]
        out = []
        for row in reader:
            value = (row.get(col) or "").strip()
            if iso_to_day(value) is not None:
                out.append(value)
    return out


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--min-length", type=float, default=DEFAULT_MIN_LENGTH)
    p.add_argument("--max-length", type=float, default=DEFAULT_MAX_LENGTH)
    p.add_argument("--mu0", type=float, default=DEFAULT_PRIOR["mu0"])
    p.add_argument("--kappa0", type=float, default=DEFAULT_PRIOR["kappa0"])
    p.add_argument("--alpha0", type=float, default=DEFAULT_PRIOR["alpha0"])
    p.add_argument("--beta0", type=float, default=DEFAULT_PRIOR["beta0"])


def prior_from_args(args: argparse.Namespace) -> dict:
    return {"mu0": args.mu0, "kappa0": args.kappa0, "alpha0": args.alpha0, "beta0": args.beta0}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("csv", help="canonical CSV with a cycle_start_date column")
    p.add_argument("--level", type=float, default=DEFAULT_LEVEL, help="credible level (default 0.8)")
    p.add_argument("--n-predicted", type=int, default=DEFAULT_N_PREDICTED)
    p.add_argument("--with-lengths", action="store_true", help="include every cycle length in the output")
    add_common_args(p)
    args = p.parse_args(argv)

    result = predict(read_dates(args.csv), level=args.level, min_length=args.min_length,
                     max_length=args.max_length, n_predicted=args.n_predicted, prior=prior_from_args(args))
    if not args.with_lengths:
        result["excluded"] = [l for l in result["lengths"] if not l["included"]]
        del result["lengths"]
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
