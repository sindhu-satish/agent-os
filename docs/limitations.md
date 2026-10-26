# Limitations

## Exactly-once side effects

Delivery and execution are at-least-once. The window is a crash after a tool handler has performed work and before the `succeeded` step row commits. Recovery retries a step left in `running`. A step already marked `succeeded` is not run again.

Builtin tools (`echo`, `add`, `multiply`, `concat`, `lookup`) are pure, so a retry returns the same result. This does not extend to a future tool that charges a card or sends an email unless that tool dedupes on execution id and step sequence.

The outbox can publish the same wake-up more than once if the process dies after JetStream accepts the message and before `published_at` is stored. The claim ignores that duplicate.

## Tenant isolation

Rows are filtered by `organization_id` in the repository used by the API. Postgres row-level security is not enabled. A new query that forgets the filter can read another tenant. Do not add a query path that bypasses the repositories.

## Tool isolation

Builtin tools run inside the worker process. A defect in a handler can read worker memory and environment variables. Docker Compose isolates that process from the laptop only to the extent of the container boundary. There is no per-tool container, no seccomp profile, and no dropped-capability sandbox yet. Agents cannot submit a shell command or a container image.

## Authentication

API keys are hashed with SHA-256. The local bootstrap key comes from `AGENTOS_BOOTSTRAP_API_KEY` and is appropriate for a development machine. There is no user signup, no key rotation API, and no per-route authorization beyond organization membership. Rate limiting is not implemented.

## Recovery scope

One worker process recovers expired leases when it runs. If no worker is running, expired work waits. Automatic retry of a `failed` execution is represented in the state machine and is not yet driven by the worker loop. Dead-letter transitions are tested as pure transitions.

## Observability and memory

There are no traces, metrics dashboards, or semantic memory queries. Checkpoints hold the working transcript for a single execution. `memory_entries.embedding` is an unused JSON column until pgvector is introduced.

## Model coverage

Only the scripted provider runs in Milestone 1. It recognizes patterns such as `add …`, `multiply …`, `add … then multiply by …`, `say …`, `greet …`, `lookup …`, and `research … and note it`. Other text is returned as the final answer without a tool call. It does not call an external model.
