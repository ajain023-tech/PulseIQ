# Contributing

1. `python3.11 -m venv .venv && source .venv/bin/activate && make install`
2. Create a branch. Keep commits small (`feat(warehouse): …`, `fix(ai): …`).
3. Run `make lint && make all-small` before opening a PR. CI runs the same steps.
4. **Never type result numbers into docs by hand.** Regenerate them (`make all`, `make results`)
   and run `make check-numbers`.
5. Library code must never read `data/raw/ground_truth.json`. Only `src/pulseiq/validation.py`
   and the tests may read it.
6. Secrets come only from environment variables. `.env` and `.streamlit/secrets.toml` are
   git-ignored.
