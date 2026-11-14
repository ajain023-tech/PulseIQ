# Final audit — PulseIQ v1.0.0 (2026-11-14)

Checks were run on the development Mac (Apple Silicon, Python 3.11 via uv) and on a **fresh
`git clone`** of the release branch with a brand-new virtualenv.

| # | Check | Result | Evidence |
|---|---|:-:|---|
| 1 | Clean clone: `make install` | ✅ | 106 s, fresh venv |
| 2 | Clean clone: `make all` (generate 60k users → dbt build → analyse → train → survival → validate → full pytest) | ✅ | 115 s; 22 models, 70 dbt tests, **98 pytest tests passed** |
| 3 | Results reproduce from the seed (clean clone) | ✅ | `render_results.py --check`: README matches *independently regenerated* artifacts |
| 4 | `scripts/check_numbers.py` (README block + numbers quoted in 4 docs + hygiene of 151 files) | ✅ | "OK" |
| 5 | `requirements.txt` in sync with `pyproject.toml` | ✅ | `export_requirements.py --check` |
| 6 | Lint and format (`ruff`, src/tests/apps/scripts) | ✅ | "All checks passed" |
| 7 | Experiment engine vs ground truth | ✅ | all planted effects covered, SRM only on `streak_reminder` → Android, CUPED ≥ 20 % (`artifacts/reports/experiment_validation.md`) |
| 8 | Retention model beats baselines; drivers recovered; leakage test | ✅ | `artifacts/reports/ml_validation.md`, `tests/test_no_leakage.py` |
| 9 | API: every endpoint tested; p95 latency | ✅ | `tests/test_api.py`; worst cached p95 12.6 ms (target < 300 ms) |
| 10 | **Dashboard page-by-page in a real browser** (headless Chromium via Playwright, full-size data) | ✅ | all 9 pages render with 0 Streamlit exceptions; screenshots in `docs/images/` |
| 11 | Dashboard cold start from an empty data dir (simulates the cloud) | ✅ | first page in 10.5 s (target < 60 s); all 9 pages pass on small data |
| 12 | Dashboard narrow filters / empty states | ✅ | `tests/test_dashboard.py` (AppTest) |
| 13 | AI analyst guardrails + eval | ✅ | 22 attack patterns blocked; mock eval 25/25 |
| 14 | No machine-specific paths, no TODO/FIXME, no foreign Tableau link in the active tree | ✅ | `check_numbers.py` hygiene scan |
| 15 | No secrets committed; `.env` and `secrets.toml` ignored | ✅ | grep for key patterns: none; `.gitignore` |
| 16 | No empty or garbled files in the active tree | ✅ | `find -empty`, `?` scan (empty v1 files remain only under `legacy/`, listed in `legacy/README.md`) |
| 17 | Legacy v1 preserved | ✅ | `legacy/` (moved with `git mv`, history intact) |
| 18 | `docker compose up --build` | ⚠️ **not run** | Docker isn't installed on the build machine. The image's entrypoint (`scripts/bootstrap.sh`) was verified from a clean clone (34 s small-mode bootstrap). Image size not measured. |
| 19 | Live deployment (Streamlit Cloud / Render) | ⏸ **waiting on you** | Configs are ready (`docs/DEPLOYMENT.md`); deploying needs your accounts |
| 20 | Real-LLM AI eval | ⏸ **waiting on you** | No API key provided; the roadmap requires asking first |
| 21 | `git push`, tag `v1.0.0` | ⏸ **waiting on you** | Merged to local `main`; push and tag need your approval |

## Exceptions explained
- **Docker (18):** the Dockerfile, compose file and `.dockerignore` follow the spec: multi-stage,
  non-root, healthcheck, shared volumes, and a one-shot `init` service with
  `service_completed_successfully`. To verify, install Docker Desktop and run
  `docker compose up --build`. Record the startup time and `docker images pulseiq` size in
  PROGRESS.md.
- **Hosted demo memory:** generating the full dataset peaks at about 4.3 GB RAM, so the hosted
  demo runs the small dataset. Its experiments are underpowered (all KEEP RUNNING); the app shows
  a banner saying so.
- **Port 8000:** on the build machine it was occupied by an unrelated local project, so the API
  was verified on :8010. The port is configurable everywhere (`PORT`, `PULSEIQ_API_PORT`).
- **GIF of the AI analyst:** skipped (on the roadmap's cut list); the screenshots cover it.
