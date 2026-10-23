# Progress

## Milestone 1: Single-worker vertical slice

Status: complete.

Verified:

- `uv run ruff check src tests examples`: all checks passed
- `uv run mypy src`: no issues
- `uv run pytest tests/unit -q`: 48 passed
- `uv run pytest tests/integration -q`: 13 passed
- `docker compose up --build` starts Postgres, NATS, the API, and one worker
- `uv run python examples/demo_task.py` completed with result `5`, then recovered an expired lease without a second tool step

GitHub Actions is configured and has not been executed here, because this history has not been pushed.

### Known limitations

See [limitations.md](limitations.md). Automatic retry of a failed execution is named in the state machine and is not driven by the worker. Tool side effects that commit after the handler returns and before the step row commits can run twice. Milestone 1 tools are pure.

## Dashboard slice (pulled forward from Milestone 4)

Status: complete for the local demo UI.

- CORS and `AGENTOS_ENABLE_DEMO_ROUTES` on the API
- `POST /v1/demo/recoveries` plus shared seeder used by `examples/demo_task.py`
- Vite/React/Tailwind dashboard with Eat Cook Joy color tokens
- Compose service on `http://127.0.0.1:5173`

### Commits

- `8f1fd61` `feat: add CORS and demo-route settings`
- `f9154df` `feat: extract demo recovery seeder and expose demo API`
- `8443b3e` `chore: scaffold React dashboard with Vite and Tailwind`
- `749ac77` `feat: add dashboard API client and connect screen`
- `dca42c7` `feat: add agents, execution workspace, and crash-recovery action`
- `1eb3983` `chore: serve dashboard from Docker Compose`
- `47d8dbb` `docs: document the local dashboard demo`

### Next feature

Milestone 2: bounded retries and dead-letter handling in the worker, then OpenTelemetry, Prometheus, Grafana, and Redis rate limiting. Full Milestone 4 still includes the tool sandbox, load generator, and measured benchmarks.
