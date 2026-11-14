# Deployment

Everything is prepared. The steps that publish something (pushing to GitHub, creating the hosted
app) are yours to run, because they use your accounts.

## 1. Docker (local, one command)

```bash
docker compose up --build            # init (bootstrap) -> api :8000 + dashboard :8501
PULSEIQ_SIZE=full docker compose up --build    # full-size data, needs ~5 GB RAM for generation
PULSEIQ_API_PORT=8010 docker compose up --build  # if port 8000 is taken on your machine
docker compose down                   # stop (add -v to delete the data volumes)
```

- The one-shot `init` service runs `scripts/bootstrap.sh`: generate → build → analyse → train.
  Data goes into named volumes, then `api` and `dashboard` start.
- The bootstrap is idempotent: later starts skip work that is already done.
- The image is `python:3.11-slim` (multi-stage) and runs as a non-root user, with a healthcheck
  on `/api/v1/health`.
- Verify:
  - `curl localhost:8000/api/v1/health` returns `"status":"ok"`;
  - http://localhost:8501 shows the dashboard.

> **Not verified in this build:** Docker isn't installed on the development machine, so the image
> was never built or measured. The same bootstrap was verified end to end from a clean clone
> without Docker (fresh venv: install 12 s, bootstrap 34 s). Run `docker compose up --build`
> once, and record the image size (`docker images pulseiq`) and the startup time.

## 2. Streamlit Community Cloud (dashboard) — primary

1. Push the repository to GitHub (`main` branch).
2. Go to https://share.streamlit.io → **Create app** → choose the repo and branch `main`.
3. **Main file path:** `apps/dashboard/Home.py`. Python version: 3.11.
4. **Advanced settings → Secrets:** paste the contents of `.streamlit/secrets.toml.example` and
   edit them. At minimum keep `PULSEIQ_SIZE = "small"`. Add an LLM key only if you want the AI
   analyst online; without one it runs in offline mode.
5. Deploy. Dependencies install from `requirements.txt`, which is generated from
   `pyproject.toml` by `make requirements` and includes `-e .` for the package.
6. On the first visit the app bootstraps: it generates the small dataset, builds the warehouse,
   analyses experiments and trains the model. A cold start measured locally from an empty
   directory took **10.5 s** to the first rendered page.
7. Put the app URL in the README badge ("live demo") and in your profiles.

**Why small mode?** Generating the full 60k-user dataset peaks at about 4.3 GB RAM, and the dbt
build at about 2.7 GB. Both are above free-tier limits. On the small dataset (4,000 users) the
experiments are underpowered, so they read KEEP RUNNING. The app says so in a banner and points
to the full-size results in the README.

## 3. Render (API) — optional

`render.yaml` defines a Docker web service, `pulseiq-api`, with health check path
`/api/v1/health`, small mode, and `GEMINI_API_KEY` as a secret you enter in the dashboard.

1. Go to https://dashboard.render.com → **New → Blueprint**, choose the repo, and apply.
2. Enter secrets when prompted (optional).
3. The free tier sleeps when idle. The first request after a sleep triggers a cold start, plus
   the bootstrap if the disk is empty.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PULSEIQ_SIZE` | `full` locally, `small` in Docker/cloud | dataset size |
| `PULSEIQ_SEED` | `42` | global seed |
| `PULSEIQ_DATA_DIR` / `PULSEIQ_ARTIFACTS_DIR` | `./data` / `./artifacts` | storage locations |
| `PULSEIQ_WAREHOUSE` | `$DATA_DIR/warehouse/pulseiq.duckdb` | warehouse file |
| `PULSEIQ_LLM_PROVIDER` | `gemini` (offline without a key) | `gemini`, `anthropic`, `openai`, `mock`, `offline` |
| `PULSEIQ_LLM_MODEL` | provider default | model override |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | – | LLM keys (secrets only) |
| `PORT` | 8000 / 8501 | service port inside the container |

## Troubleshooting

- **"Warehouse not found":** run `pulseiq generate --small && pulseiq build`, or restart the
  container so the bootstrap runs.
- **Out of memory on the cloud:** make sure `PULSEIQ_SIZE=small`.
- **Port 8000 in use:** use `make serve PORT=8010`, or set `PULSEIQ_API_PORT=8010` for compose.
- **AI analyst says "offline mode":** no key is set. This is expected. Add a key to the
  secrets / `.env`.
- **Slow first page:** a cold start is running the bootstrap. Later loads are cached.
