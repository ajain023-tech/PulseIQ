#!/usr/bin/env sh
# Idempotent bootstrap: build data + warehouse + analyses + model if missing, then exec
# the requested service.  Usage: scripts/bootstrap.sh [api|dashboard|init]
set -eu
SERVICE="${1:-init}"
SIZE="${PULSEIQ_SIZE:-small}"
DATA_DIR="${PULSEIQ_DATA_DIR:-data}"
ARTIFACTS_DIR="${PULSEIQ_ARTIFACTS_DIR:-artifacts}"
WAREHOUSE="${PULSEIQ_WAREHOUSE:-$DATA_DIR/warehouse/pulseiq.duckdb}"

if [ ! -f "$WAREHOUSE" ]; then
  echo "[bootstrap] no warehouse at $WAREHOUSE -> generating ($SIZE) and building"
  if [ "$SIZE" = "small" ]; then pulseiq generate --small; else pulseiq generate; fi
  pulseiq build
fi
if [ ! -f "$ARTIFACTS_DIR/experiments/paywall_redesign/report.json" ]; then
  echo "[bootstrap] analysing experiments"
  pulseiq analyze --all
fi
if [ ! -f "$ARTIFACTS_DIR/ml/model.joblib" ]; then
  echo "[bootstrap] training the retention model"
  pulseiq train
  pulseiq survival
fi
echo "[bootstrap] ready"

case "$SERVICE" in
  api) exec pulseiq serve --host 0.0.0.0 --port "${PORT:-8000}" ;;
  dashboard) exec streamlit run apps/dashboard/Home.py --server.address 0.0.0.0 --server.port "${PORT:-8501}" ;;
  init) exit 0 ;;
  *) echo "unknown service: $SERVICE" >&2; exit 2 ;;
esac
