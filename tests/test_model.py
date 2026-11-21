"""Unit tests for the Python model (pipeline/fit_model.py)."""
import math

import pytest

from fit_model import (DEFAULT_PRIOR, fit_nig, norm_quantile, predict, predictive,
                       round_half_up, t_quantile)


@pytest.mark.parametrize("p, nu, expected", [
    (0.9, 4, 1.533206),
    (0.975, 10, 2.228139),
    (0.95, 1, 6.313752),
    (0.9, 42, 1.302036),
    (0.1, 4, -1.533206),
])
def test_t_quantile_matches_tables(p, nu, expected):
    assert t_quantile(p, nu) == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize("p, expected", [(0.9, 1.2815516), (0.975, 1.9599640), (0.01, -2.3263479)])
def test_normal_quantile(p, expected):
    assert norm_quantile(p) == pytest.approx(expected, abs=1e-6)


def test_normal_fallback_for_large_nu():
    assert t_quantile(0.9, 5000) == norm_quantile(0.9)
    assert t_quantile(0.9, 999) == pytest.approx(norm_quantile(0.9), abs=2e-3)


def test_posterior_by_hand():
    lengths = [27, 29, 31]
    post = fit_nig(lengths, DEFAULT_PRIOR)
    # mean 29, S = 8, m = 3
    assert post["kappa_n"] == 4
    assert post["mu_n"] == pytest.approx((28 + 3 * 29) / 4)
    assert post["alpha_n"] == 3.5
    assert post["beta_n"] == pytest.approx(16 + 4 + (1 * 3 * 1) / (2 * 4))
    pred = predictive(post)
    assert pred["nu"] == 7
    assert pred["scale"] == pytest.approx(math.sqrt(post["beta_n"] * 5 / (3.5 * 4)))


def test_prior_only_with_one_date():
    r = predict(["2024-01-01"])
    assert r["prior_only"] is True
    assert r["m"] == 0
    assert r["next_date"] == "2024-01-29"  # + round(28)
    # prior predictive: nu = 4, scale = sqrt(16 * 2 / (2 * 1)) = 4 -> +/- 1.533 * 4 days
    assert r["scale"] == pytest.approx(4.0)
    assert r["lo_date"] == "2024-01-23" and r["hi_date"] == "2024-02-04"


def test_no_dates():
    r = predict([])
    assert r["n_dates"] == 0 and r["next_date"] is None and r["upcoming"] == []


def test_hygiene_excludes_out_of_range_lengths():
    dates = ["2024-01-01", "2024-01-29", "2024-02-05", "2024-03-04", "2024-07-01"]
    r = predict(dates)  # lengths 28, 7 (out), 28, 120 (out)
    assert r["n_excluded"] == 2
    assert r["m"] == 2
    assert r["mean"] == 28
    r2 = predict(dates, min_length=5, max_length=200)
    assert r2["n_excluded"] == 0 and r2["m"] == 4


def test_duplicates_and_order_do_not_matter():
    a = predict(["2024-03-01", "2024-01-01", "2024-01-30", "2024-01-30"])
    b = predict(["2024-01-01", "2024-01-30", "2024-03-01"])
    assert a == b


def test_round_half_up():
    assert round_half_up(2.5) == 3 and round_half_up(-2.5) == -2 and round_half_up(28.49) == 28
