# PulseIQ — Product Analytics & Experimentation Platform

> Status: **Phase 1 of 4 complete** (foundation: package, event generator, DuckDB + dbt
> warehouse, tests, CI). The full README is written in Phase 4.

PulseIQ simulates a fitness/habit subscription app with **known ground truth**,
builds a tested **DuckDB + dbt** warehouse, and (in later phases) analyses
experiments, predicts retention, serves an API and dashboard, and answers questions
through an AI analyst.

## Quickstart

```bash
python3.11 -m venv .venv && source .venv/bin/activate
make install          # pip install -e ".[dev]"
make all              # generate (60k users) -> dbt build (models + tests) -> pytest
# or the fast path:
make all-small        # 4k users, ~5 s
pulseiq profile       # mart row counts + headline KPIs
```

Docs: [event schema](docs/EVENT_SCHEMA.md) · [data generation](docs/DATA_GENERATION.md) ·
[warehouse](docs/WAREHOUSE.md) · [SQL migration](docs/SQL_MIGRATION.md) ·
[roadmap](docs/roadmap/README.md) · [progress log](docs/roadmap/PROGRESS.md)

The original v1 analysis is preserved in [`legacy/`](legacy/README.md).

Tableau: TBD
