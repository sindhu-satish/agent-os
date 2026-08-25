# Design decisions

## Modular monolith with two processes

The product lists eight services. Running them as eight deployable services would require distributed transactions before a single task can finish. Packages keep those boundaries. The API and the worker are the only processes. Postgres is shared.

The cost is that a bad deploy ships both entrypoints together. The gain is one transactional write path for task submission.

## Transactional outbox

The request writes the task and the outbox row together. Publishing happens afterward. If NATS is down, the task remains queued and the publisher retries. JetStream delivery is at-least-once. The claim is conditional, so a duplicate message does not create a second owner.

Publishing inside the request was rejected because a committed task and a failed publish would need a second reconciliation anyway. The outbox makes that reconciliation the normal path.

## Lease fencing in Postgres

A Redis heartbeat disappears when Redis does. The lease row and the fencing token live next to the execution. Stale workers fail their writes because the token no longer matches. Redis remains the planned home for rate-limit counters, not for ownership.

## Scripted model provider

The acceptance path must run locally without a paid API key. `ModelProvider` is the extension point. A live adapter can be added behind it without changing the engine. The scripted provider returns fixed token counts so budget checks are exercisable.

## In-process allowlisted tools

A container per tool call is a separate security project. Milestone 1 handlers are pure functions selected by `handler_key`. There is no `eval` and no shell. The Docker boundary is the worker container, documented as such.

## Application-level tenant filters

Repository methods take `organization_id` from the authenticated key and put it in the query. Row-level security is stronger and will be added when the query surface is stable. Shipping RLS policy for unused tables before the queries exist would drift from the code.

## One image, two commands

The API container runs `alembic upgrade head` and then Uvicorn. The worker container runs `python -m agentos.worker`. Only the API process migrates. Alembic upgrades are idempotent for the single API replica in this milestone.

## Exactly-once is not claimed

A crash after a tool handler returns and before the step row commits can run that handler again. Milestone 1 tools are pure, so replay is safe. Handlers declare `idempotent`. A future non-idempotent tool must tolerate the retry or move the side effect behind its own idempotency key. The execution id plus step sequence is that key for recorded steps that have already reached `succeeded`.
