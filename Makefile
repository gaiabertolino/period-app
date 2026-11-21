.PHONY: run test serve icons sample clean

DATA ?= data/sample_synthetic.csv

run:            ## validate + fit + backtest + tests
	./run.sh $(DATA)

test:
	./run.sh >/dev/null && .venv/bin/python -m pytest -v tests

serve:          ## serve the app at http://localhost:8000
	cd app && python3 -m http.server 8000

icons:
	python3 tools/make_icons.py

sample:
	python3 pipeline/make_synthetic.py

clean:
	rm -rf .venv out .pytest_cache tests/__pycache__ pipeline/__pycache__
