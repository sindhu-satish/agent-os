import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  cancelTask,
  createAgent,
  createDemoRecovery,
  createTask,
  getExecution,
  listAgents,
  type Agent,
  type Execution,
  type Session,
} from "./api";
import { isTerminal, statusChipStyle, stepKindStyle } from "./statusStyles";

type Props = {
  session: Session;
  onDisconnect: () => void;
};

export function Workspace({ session, onDisconnect }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("Calculator");
  const [slug, setSlug] = useState(`calc-${crypto.randomUUID().slice(0, 8)}`);
  const [taskText, setTaskText] = useState("add 2 and 3");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = agents.find((agent) => agent.id === selectedId) ?? null;

  const refreshAgents = useCallback(async () => {
    const next = await listAgents(session);
    setAgents(next);
    setSelectedId((current) => current ?? next[0]?.id ?? null);
  }, [session]);

  useEffect(() => {
    void refreshAgents().catch((err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Failed to load agents");
    });
  }, [refreshAgents]);

  useEffect(() => {
    if (!executionId) {
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const next = await getExecution(session, executionId!);
        if (cancelled) {
          return;
        }
        setExecution(next);
        if (!isTerminal(next.status)) {
          timer = window.setTimeout(() => {
            void poll();
          }, 500);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to poll execution");
        }
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [executionId, session]);

  async function handleCreateAgent(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const agent = await createAgent(session, {
        name: name.trim(),
        slug: slug.trim(),
        tool_names: ["add"],
      });
      await refreshAgents();
      setSelectedId(agent.id);
      setSlug(`calc-${crypto.randomUUID().slice(0, 8)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create agent");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitTask(event: FormEvent) {
    event.preventDefault();
    if (!selected) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const task = await createTask(session, {
        agent_id: selected.id,
        input: { text: taskText.trim() },
        idempotency_key: `ui-${crypto.randomUUID()}`,
      });
      setTaskId(task.id);
      setExecutionId(task.execution_id);
      setExecution(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit task");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!taskId) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await cancelTask(session, taskId);
      if (executionId) {
        const next = await getExecution(session, executionId);
        setExecution(next);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel task");
    } finally {
      setBusy(false);
    }
  }

  async function handleSimulateCrash() {
    if (!selected) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const seeded = await createDemoRecovery(session, selected.id);
      setTaskId(null);
      setExecution(null);
      setExecutionId(seeded.execution_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not seed crash recovery");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen px-4 py-8 md:px-8">
      <header className="mx-auto flex max-w-6xl items-end justify-between gap-4 border-b border-[var(--black-10)] pb-6">
        <div>
          <p className="font-[family-name:var(--font-display)] text-4xl tracking-tight">AgentOS</p>
          <p className="mt-1 text-[var(--black-4)]">Agents, tasks, and execution timeline</p>
        </div>
        <button
          type="button"
          onClick={onDisconnect}
          className="border border-[var(--black-10)] bg-[var(--beige-4)] px-3 py-2 text-sm"
        >
          Disconnect
        </button>
      </header>

      <div className="mx-auto mt-8 grid max-w-6xl gap-8 lg:grid-cols-[280px_1fr]">
        <section className="space-y-6">
          <form
            onSubmit={handleCreateAgent}
            className="space-y-3 border border-[var(--black-10)] bg-[var(--beige-4)] p-4"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--black-4)]">
              New agent
            </h2>
            <input
              className="w-full border border-[var(--black-10)] bg-[var(--beige-5)] px-3 py-2"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Name"
              required
            />
            <input
              className="w-full border border-[var(--black-10)] bg-[var(--beige-5)] px-3 py-2 font-[family-name:var(--font-mono)] text-sm"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder="slug"
              required
            />
            <p className="text-xs text-[var(--black-5)]">Tools: add · provider: scripted</p>
            <button
              type="submit"
              disabled={busy}
              className="bg-[var(--cta)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Create agent
            </button>
          </form>

          <div className="border border-[var(--black-10)] bg-[var(--beige-4)]">
            <h2 className="border-b border-[var(--black-10)] px-4 py-3 text-sm font-semibold uppercase tracking-wide text-[var(--black-4)]">
              Agents
            </h2>
            <ul>
              {agents.length === 0 ? (
                <li className="px-4 py-6 text-sm text-[var(--black-5)]">No agents yet.</li>
              ) : (
                agents.map((agent) => {
                  const active = agent.id === selectedId;
                  return (
                    <li key={agent.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(agent.id)}
                        className={`w-full border-b border-[var(--black-11)] px-4 py-3 text-left ${
                          active ? "bg-[var(--beige-3)]" : "bg-transparent hover:bg-[var(--beige-5)]"
                        }`}
                      >
                        <span className="block font-medium">{agent.name}</span>
                        <span className="mt-1 block font-[family-name:var(--font-mono)] text-xs text-[var(--black-5)]">
                          {agent.slug}
                        </span>
                      </button>
                    </li>
                  );
                })
              )}
            </ul>
          </div>
        </section>

        <section className="space-y-6">
          <form
            onSubmit={handleSubmitTask}
            className="space-y-3 border border-[var(--black-10)] bg-[var(--beige-4)] p-4"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--black-4)]">
              Submit task
            </h2>
            {selected ? (
              <p className="font-[family-name:var(--font-mono)] text-xs text-[var(--black-5)]">
                agent {selected.id}
              </p>
            ) : (
              <p className="text-sm text-[var(--black-5)]">Select or create an agent first.</p>
            )}
            <textarea
              className="min-h-24 w-full border border-[var(--black-10)] bg-[var(--beige-5)] px-3 py-2"
              value={taskText}
              onChange={(event) => setTaskText(event.target.value)}
              required
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={busy || !selected}
                className="bg-[var(--cta)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Submit
              </button>
              <button
                type="button"
                onClick={() => void handleCancel()}
                disabled={busy || !taskId}
                className="border border-[var(--black-10)] bg-[var(--beige-5)] px-4 py-2 text-sm disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSimulateCrash()}
                disabled={busy || !selected}
                className="border border-[var(--cta)] bg-[var(--beige-5)] px-4 py-2 text-sm font-semibold text-[var(--cta)] disabled:opacity-50"
              >
                Simulate crash recovery
              </button>
            </div>
          </form>

          <ExecutionPanel execution={execution} executionId={executionId} />
        </section>
      </div>

      {error ? (
        <p className="mx-auto mt-6 max-w-6xl text-sm text-[var(--sweet-dark)]" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ExecutionPanel({
  execution,
  executionId,
}: {
  execution: Execution | null;
  executionId: string | null;
}) {
  if (!executionId) {
    return (
      <div className="border border-[var(--black-10)] bg-[var(--beige-4)] p-6 text-sm text-[var(--black-5)]">
        Submit a task to watch its execution timeline.
      </div>
    );
  }

  if (!execution) {
    return (
      <div className="border border-[var(--black-10)] bg-[var(--beige-4)] p-6 text-sm text-[var(--black-5)]">
        Loading execution…
      </div>
    );
  }

  const chip = statusChipStyle(execution.status);
  return (
    <div className="border border-[var(--black-10)] bg-[var(--beige-4)]">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--black-10)] px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--black-4)]">
          Execution
        </h2>
        <span
          className="rounded-sm px-2 py-0.5 text-xs font-semibold uppercase tracking-wide"
          style={chip}
        >
          {execution.status}
        </span>
        <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--black-5)]">
          {execution.id}
        </span>
      </div>

      {(execution.result || execution.error) && (
        <div className="border-b border-[var(--black-10)] px-4 py-3 text-sm">
          {execution.result ? (
            <pre className="overflow-x-auto font-[family-name:var(--font-mono)] text-xs">
              {JSON.stringify(execution.result, null, 2)}
            </pre>
          ) : null}
          {execution.error ? (
            <p className="text-[var(--sweet-dark)]">{execution.error}</p>
          ) : null}
        </div>
      )}

      <ol className="divide-y divide-[var(--black-11)]">
        {execution.steps.length === 0 ? (
          <li className="px-4 py-6 text-sm text-[var(--black-5)]">No steps yet.</li>
        ) : (
          execution.steps.map((step) => {
            const kind = stepKindStyle(step.kind);
            const status = statusChipStyle(step.status);
            return (
              <li key={step.sequence} className="px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--black-5)]">
                    #{step.sequence}
                  </span>
                  <span className="rounded-sm px-2 py-0.5 text-xs font-semibold" style={kind}>
                    {step.kind}
                  </span>
                  <span className="text-sm font-medium">{step.name}</span>
                  <span className="rounded-sm px-2 py-0.5 text-xs font-semibold" style={status}>
                    {step.status}
                  </span>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <pre className="overflow-x-auto bg-[var(--beige-5)] p-2 font-[family-name:var(--font-mono)] text-[11px]">
                    {JSON.stringify(step.input, null, 2)}
                  </pre>
                  <pre className="overflow-x-auto bg-[var(--beige-5)] p-2 font-[family-name:var(--font-mono)] text-[11px]">
                    {JSON.stringify(step.output, null, 2)}
                  </pre>
                </div>
              </li>
            );
          })
        )}
      </ol>
    </div>
  );
}
