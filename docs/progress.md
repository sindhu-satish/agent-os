# Progress

## Milestone 1: Single-worker vertical slice

Status: complete.

Verified on this machine after `b3ad4230ad0f184616806ce82d5c34129e9bfb7f`:

- `uv run ruff check src tests examples`: all checks passed
- `uv run mypy src`: no issues in 41 source files
- `uv run pytest tests/unit -q`: 47 passed
- `uv run pytest tests/integration -q`: 10 passed
- `docker compose up --build` started Postgres, NATS, the API, and one worker. The API became healthy.
- `uv run python examples/demo_task.py` completed one execution with result `5`, then recovered an expired lease without a second tool step.

GitHub Actions is configured and has not been executed here, because this history has not been pushed.

### Commits

- `72c7424d022cdc8699e510746b40e197cc1b6f91` `chore: initialize project structure and development tooling`
- `ab2ad66aeccc22689081829c0209a1eb08deef19` `docs: document architecture and milestone plan`
- `89d25b23e5202ca1f1eda0a1e81c670e23eb77cc` `feat: implement application configuration`
- `f0f3d21e1cd6608a30f7fab911ca863570333183` `feat: add structured logging and health endpoints`
- `656fccc615942a3af294e79434aa2c494a0db210` `feat: add database models and initial migration`
- `323d80c7e6ff4377c80dd836215e7e403ad7af5d` `feat: implement repositories for agents, tasks, and leases`
- `4047bdfd949f49a421d5282e5b687e76ce5ed090` `feat: implement execution state machine`
- `9c00ad05572195e6de1423585161ddc446c995d8` `feat: implement transactional outbox and JetStream publisher`
- `89fea8fcf7cd5d162ca0948a4bed127cb301dadc` `feat: implement tool gateway and builtin tools`
- `3b1185d11541b8c069f29d0a0c9a22e561525fb5` `feat: implement scripted provider and execution engine`
- `5a52b95cc42e43122f83bd9494082ca66e4a018a` `feat: expose agent, task, and execution APIs`
- `9644efeaabe66ae80fbb028ef14e2bb4f3db0578` `feat: implement single-worker runtime and lease recovery`
- `40e33c0f0dc35012f7fec60dc5830f21d74664a3` `feat: add local end-to-end demo script`
- `b3ad4230ad0f184616806ce82d5c34129e9bfb7f` `ci: run lint, types, and tests in GitHub Actions`

### Known limitations

See [limitations.md](limitations.md). Automatic retry of a failed execution is named in the state machine and is not driven by the worker. Tool side effects that commit after the handler returns and before the step row commits can run twice. Milestone 1 tools are pure.

### Next feature

Milestone 2: bounded retries and dead-letter handling in the worker, then OpenTelemetry, Prometheus, Grafana, and Redis rate limiting.
