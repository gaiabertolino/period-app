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
    out = subprocess.run([NODE, str(RUNNER), *args], capture_output=True, text=True, check=True)
    return out.stdout


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
