# Implementation plan

Milestone 1 is the only milestone under construction. Later milestones are sequenced so the vertical slice stays runnable.

## Milestone 1: Single-worker vertical slice

Objective: a developer can start Postgres and NATS, register an agent, submit tasks, watch a worker finish them, and recover an execution after its lease expires without repeating completed steps.

Features, in commit order:

1. `chore: initialize project structure and development tooling`
2. `docs: document architecture and milestone plan`
3. `feat: implement application configuration`
4. `feat: add structured logging and health endpoints`
5. `feat: add database models and initial migration`
6. `feat: implement repositories for agents, tasks, and leases`
7. `feat: implement execution state machine`
8. `feat: implement transactional outbox and JetStream publisher`
9. `feat: implement tool gateway and builtin tools`
10. `feat: implement scripted provider and execution engine`
11. `feat: expose agent, task, and execution APIs`
12. `feat: implement single-worker runtime and lease recovery`
13. `feat: add local end-to-end demo script`
14. `ci: run lint, types, and tests in GitHub Actions`
15. `docs: record milestone 1 verification`

Dependencies: configuration before the API. The schema before repositories. The state machine before the engine applies transitions. The tool gateway and provider before the engine. The engine before the worker. The API can persist tasks before the worker is running.

Acceptance: see the root README once verification is recorded. Tests required: state-machine unit tests, tool-gateway unit tests, engine resume tests on a fake store, repository concurrency against Postgres, outbox publish against NATS, API tests, and a simulated expired-lease recovery.

Risks: lease queries must use row locks. The fencing token must be on the same update as the step write. NATS must not be treated as the source of truth.

## Milestone 2: Reliability and observability

Bounded automatic retries and dead-letter from the worker loop, OpenTelemetry across the API and worker, Prometheus metrics, Grafana provisioning, Redis rate limiting, and per-tenant concurrency quotas. The state machine already names retry and dead-letter transitions.

## Milestone 3: Memory and providers

pgvector retrieval over `memory_entries`, retention, agent version rollback, and optional live model adapters behind `ModelProvider`.

## Milestone 4: Isolation, dashboard, and benchmarks

A non-root tool sandbox with no host mounts and no Docker socket. A React dashboard for agents, timelines, and failures. A load generator. [benchmarks.md](benchmarks.md) receives measured numbers only after a run.

Pulled forward after Milestone 1: a local Vite/React dashboard (agents, task submit, execution timeline, crash-recovery button) plus gated `POST /v1/demo/recoveries`. Sandbox isolation, load generator, and measured benchmarks remain in this milestone.

## Milestone 5: Optional research

Multi-agent messages, human approval gates, execution replay, and autoscaling. These stay out of the tree until that milestone starts.
