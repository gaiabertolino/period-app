#!/usr/bin/env bash
# One command, from a fresh clone: set up, validate, fit, backtest, test.
#   ./run.sh                      # uses data/sample_synthetic.csv
#   ./run.sh data/private/me.csv  # your own data (stays on your machine)
set -euo pipefail
cd "$(dirname "$0")"

DATA="${1:-data/sample_synthetic.csv}"
PYTHON="${PYTHON:-python3}"

if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

mkdir -p out
echo "== validate =="
.venv/bin/python pipeline/validate_csv.py "$DATA"
echo "== fit =="
.venv/bin/python pipeline/fit_model.py "$DATA" | tee out/fit.json
echo "== backtest =="
.venv/bin/python pipeline/evaluate.py "$DATA" | tee out/evaluate.txt
.venv/bin/python pipeline/evaluate.py "$DATA" --json > out/evaluate.json
echo "== tests =="
.venv/bin/python -m pytest -q tests
echo "Done. Results in out/."
