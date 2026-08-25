# Benchmarks

No measurements are recorded yet. This file defines the method. Numbers will be added only after a run, including runs that miss a target.

## Environment to record

- Machine model, CPU, RAM, and OS
- Python version and the AgentOS git revision
- Postgres, NATS, and Docker versions
- Worker count and `max_concurrency`
- Whether the scripted provider or a live model is under test

## Workload

A load generator will submit tasks at a configured arrival rate. Each task uses the scripted provider and the `add` tool so model latency is not confused with runtime overhead. Task duration will be configurable by repeating a pure tool or by a test-only delay in a later milestone. Milestone 1 does not include that generator.

## Metrics

- Scheduling latency: task `created_at` to execution `leased` time
- Queue wait: `created_at` to `running`
- Concurrent capacity: in-flight executions before claim refusals caused by `max_concurrency`
- Worker utilization: time in `running` divided by wall clock for the worker process
- Recovery time: lease `expires_at` to the execution returning to `running` or `succeeded`
- Success rate: terminal `succeeded` divided by submitted tasks, with failures classified
- P95 execution overhead: engine time minus the scripted provider's synthetic work

## Baseline

The baseline is a single worker, one agent, `max_concurrency` 1, and the scripted provider on local Docker Compose. Later runs compare against that baseline on the same machine. Do not compare a laptop run with a cloud run without stating both environments.
