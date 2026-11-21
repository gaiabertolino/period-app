"""Parity between app/js/model.js (run under Node) and pipeline/fit_model.py.

Requires Node >= 18. Skipped locally when Node is missing, but fails in CI
(where CI=true) so the check can't be silently skipped there.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fit_model import predict, read_dates, t_quantile

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "parity_runner.mjs"
SAMPLE = ROOT / "data" / "sample_synthetic.csv"
FLOAT_KEYS = ["mean", "S", "kappa_n", "mu_n", "alpha_n", "beta_n", "nu", "scale", "q",
              "lo_len", "hi_len", "sigma"]
EXACT_KEYS = ["n_dates", "m", "n_excluded", "prior_only", "last_date", "next_date",
              "lo_date", "hi_date", "upcoming", "lengths"]

NODE = shutil.which("node")
if NODE is None and os.environ.get("CI"):
    raise RuntimeError("Node is required for the parity test in CI")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def run_js(*args: str) -> str:
    out = subprocess.run([NODE, str(RUNNER), *args], capture_output=True, check=True)
    return out.stdout.decode("utf-8")  # bytes: keep CRLF intact for .ics checks


@pytest.mark.parametrize("limit", [0, 1, 2, 3, 5, 17, 30, None])
@pytest.mark.parametrize("level", [0.5, 0.8, 0.95])
def test_predict_parity(limit, level):
    args = ["predict", str(SAMPLE), "--level", str(level)]
    dates = read_dates(str(SAMPLE))
    if limit is not None:
        args += ["--limit", str(limit)]
        dates = dates[:limit]
    js = json.loads(run_js(*args))
    py = predict(dates, level=level)
    for key in FLOAT_KEYS:
        if py[key] is None:
            assert js[key] is None, key
        else:
            assert js[key] == pytest.approx(py[key], rel=1e-9, abs=1e-9), key
    for key in EXACT_KEYS:
        assert js[key] == py[key], key


def test_custom_thresholds_parity():
    js = json.loads(run_js("predict", str(SAMPLE), "--min", "5", "--max", "120"))
    py = predict(read_dates(str(SAMPLE)), min_length=5, max_length=120)
    assert js["m"] == py["m"] and js["n_excluded"] == py["n_excluded"] == 0
    assert js["mu_n"] == pytest.approx(py["mu_n"], rel=1e-12)


@pytest.mark.parametrize("p, nu", [(0.75, 4), (0.9, 7.5), (0.975, 2), (0.995, 60), (0.9, 2000)])
def test_quantile_parity(p, nu):
    js = json.loads(run_js("quantile", "-", str(p), str(nu)))
    assert js == pytest.approx(t_quantile(p, nu), rel=1e-10)


def test_csv_roundtrip_is_identical():
    # Export of an imported canonical CSV must equal the original file.
    assert run_js("roundtrip", str(SAMPLE)) == SAMPLE.read_text(encoding="utf-8")


def test_csv_roundtrip_quoting(tmp_path):
    src = tmp_path / "q.csv"
    src.write_text('cycle_start_date,notes\n2024-01-01,"a, b"\n2024-01-29,"say ""hi"""\n', encoding="utf-8")
    assert run_js("roundtrip", str(src)) == src.read_text(encoding="utf-8")


def test_ics_all_day_events_with_configurable_alerts():
    out = run_js("ics", "-", json.dumps({"summary": "Personal reminder", "sequence": 4,
                                         "alertDays": [0, 7, 3], "alertTime": "09:00"}),
                 "2026-12-01", "2026-12-31")
    assert out.count("BEGIN:VEVENT") == 2
    assert "DTSTART;VALUE=DATE:20261201\r\nDTEND;VALUE=DATE:20261202\r\n" in out
    triggers = [l for l in out.split("\r\n") if l.startswith("TRIGGER:")]
    assert triggers == ["TRIGGER:-P6DT15H", "TRIGGER:-P2DT15H", "TRIGGER:PT9H"] * 2
    assert "DESCRIPTION:Personal reminder (in 7 days)" in out
    assert "UID:cycle-pred-2@cycle-app\r\nSEQUENCE:4" in out
    # other times and no alerts
    one = run_js("ics", "-", json.dumps({"alertDays": [1], "alertTime": "20:30"}), "2026-12-01")
    assert "TRIGGER:-PT3H30M" in one
    none = run_js("ics", "-", json.dumps({"alertDays": []}), "2026-12-01")
    assert "VALARM" not in none


def test_shortcut_payload():
    out = run_js("shortcut", "-", json.dumps({"summary": "Personal | reminder", "alertDays": [0, 7, 3],
                                               "alertTime": "09:00"}), "2026-12-01", "2026-12-31")
    *lines, url = out.split("\n")
    assert lines == [
        # 24 Nov 09:00 is before "now" (25 Nov 12:00), so it is left out
        "event|2026-12-01|Personal reminder",
        "alert|2026-11-28 09:00|Personal reminder (in 3 days)",
        "alert|2026-12-01 09:00|Personal reminder",
        "event|2026-12-31|Personal reminder",
        "alert|2026-12-24 09:00|Personal reminder (in 7 days)",
        "alert|2026-12-28 09:00|Personal reminder (in 3 days)",
        "alert|2026-12-31 09:00|Personal reminder",
    ]
    assert url == "shortcuts://run-shortcut?name=Cycle%20Sync&input=text&text=a%7Cb%0Ac"
