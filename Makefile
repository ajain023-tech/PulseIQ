# PulseIQ developer commands. Run `make help` for a list.
PY ?= python
PIP ?= $(PY) -m pip

.PHONY: help install generate generate-small build analyze train survival validate pipeline test test-fast lint format all all-small clean serve dashboard screenshots requirements results check-numbers docker-build docker-up docker-down

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install:  ## Install the package with dev extras (editable)
	$(PIP) install -e ".[dev]"

generate:  ## Generate the full dataset (60k users / 120 days)
	pulseiq generate

generate-small:  ## Generate the small dataset (4k users / 60 days)
	pulseiq generate --small

build:  ## dbt build: models + data tests into data/warehouse/pulseiq.duckdb
	pulseiq build

analyze:  ## Analyse every experiment -> artifacts/experiments/
	pulseiq analyze --all

train:  ## Train + evaluate the D30 retention model -> artifacts/ml/
	pulseiq train

survival:  ## Kaplan-Meier / Cox time-to-churn -> artifacts/ml/
	pulseiq survival

validate:  ## Compare engine + model with planted ground truth -> artifacts/reports/
	pulseiq validate

pipeline: analyze train survival validate  ## All analysis steps on an existing warehouse

test:  ## Run the whole pytest suite (includes slow tests)
	pytest -q

test-fast:  ## Run tests excluding slow ones
	pytest -q -m "not slow"

lint:  ## Lint and check formatting
	ruff check src tests apps scripts
	ruff format --check src tests apps scripts

format:  ## Auto-format code
	ruff check --fix src tests apps scripts
	ruff format src tests apps scripts

all: generate build pipeline test  ## Generate + build + analyse + train + test (full size)

all-small: generate-small build pipeline test-fast  ## Fast end-to-end run (small data)

serve:  ## Run the API on :8000 (override: make serve PORT=8010)
	pulseiq serve --port $(or $(PORT),8000)

dashboard:  ## Run the Streamlit dashboard on :8501
	streamlit run apps/dashboard/Home.py

screenshots:  ## Capture every dashboard page into docs/images (dashboard must be running)
	python scripts/screenshots.py

requirements:  ## Export requirements.txt (Streamlit Cloud) from pyproject.toml
	python scripts/export_requirements.py

results:  ## Insert generated results into README.md
	python scripts/render_results.py

check-numbers:  ## Verify README / docs numbers match artifacts
	python scripts/render_results.py --check
	python scripts/check_numbers.py

docker-build:  ## Build the Docker image
	docker build -t pulseiq:latest .

docker-up:  ## Start init + api + dashboard with docker compose
	docker compose up --build -d

docker-down:  ## Stop the compose stack
	docker compose down

clean:  ## Remove generated data and artifacts (never source code)
	rm -rf data/raw data/warehouse artifacts warehouse/target warehouse/logs
