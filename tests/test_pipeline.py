"""Smoke tests for validate_csv, parse_flo and evaluate."""
import json
from pathlib import Path

import evaluate
import parse_flo
import validate_csv
from fit_model import read_dates

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_synthetic.csv"


def test_sample_is_valid_with_flagged_outliers():
    errors, warnings, n = validate_csv.validate(str(SAMPLE), 15, 90)
    assert errors == []
    assert n == 42
    assert sum("excluded from the model" in w for w in warnings) == 3


def test_validate_reports_errors(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("cycle_start_date\n2024-01-01\n2024-02-30\n2024-01-01\n", encoding="utf-8")
    errors, _, _ = validate_csv.validate(str(f), 15, 90)
    assert any("invalid date" in e for e in errors)
    assert any("duplicate" in e for e in errors)


def test_missing_header(tmp_path):
    f = tmp_path / "nohead.csv"
    f.write_text("date\n2024-01-01\n", encoding="utf-8")
    errors, _, _ = validate_csv.validate(str(f), 15, 90)
    assert errors and "missing required header" in errors[0]


def test_parse_flo_json_daily_entries(tmp_path):
    export = {"user": {"created": "2020-05-05"}, "periods": [
        {"period_start_date": "2024-01-03T00:00:00Z", "period_end_date": "2024-01-07"},
        {"period_start_date": "2024-01-31", "period_end_date": "2024-02-04"},
    ]}
    src = tmp_path / "flo.json"
    src.write_text(json.dumps(export), encoding="utf-8")
    out = tmp_path / "out.csv"
    assert parse_flo.main([str(src), "-o", str(out)]) == 0
    assert out.read_text() == "cycle_start_date\n2024-01-03\n2024-01-31\n"


def test_parse_flo_text_collapses_consecutive_days(tmp_path):
    src = tmp_path / "flo.txt"
    src.write_text("Period: 03.01.2024\nPeriod: 04.01.2024\nPeriod: 05.01.2024\n"
                   "Period: 31.01.2024\nPeriod: 01.02.2024\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    assert parse_flo.main([str(src), "-o", str(out)]) == 0
    assert out.read_text() == "cycle_start_date\n2024-01-03\n2024-01-31\n"


def test_backtest_runs_and_is_sane():
    res = evaluate.backtest(read_dates(str(SAMPLE)), [0.8], 2, 15, 90,
                            {"mu0": 28, "kappa0": 1, "alpha0": 2, "beta0": 16})
    assert res["n_predictions"] > 30
    assert 0 < res["mae_days"] < 5
    assert 0.6 <= res["coverage"]["0.8"] <= 1.0


def test_parse_flo_txt_report_shifts_utc_midnight(tmp_path):
    src = tmp_path / "res.txt"
    src.write_text(
        "cycle 0\nPeriod start date: 2013-11-08 23:00:00.0\nPeriod end date: 2013-11-12 23:00:00.0\n"
        "Pregnant: False\n---------------\n"
        "cycle 1\nPeriod start date: 2013-12-11 23:00:00.0\nPeriod end date: 2013-12-15 23:00:00.0\n"
        "---------------\n"
        "cycle 2\nPeriod start date: 2014-01-13 00:00:00.0\nPeriod end date: 2014-01-15 00:00:00.0\n"
        "manual events\n0 - 2022-09-20 00:16:33 - 2022-09-20 00:16:33 - Sleep - Sleep - value=371\n",
        encoding="utf-8")
    out = tmp_path / "out.csv"
    assert parse_flo.main([str(src), "-o", str(out)]) == 0
    assert out.read_text() == ("cycle_start_date,period_length\n"
                               "2013-11-09,5\n2013-12-12,5\n2014-01-13,3\n")
