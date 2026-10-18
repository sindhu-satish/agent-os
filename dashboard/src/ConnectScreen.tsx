import { useState, type FormEvent } from "react";

import { ApiError, checkReady, type Session } from "./api";

type Props = {
  onConnect: (session: Session) => void;
};

export function ConnectScreen({ onConnect }: Props) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("local-dev-key");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const session: Session = {
      baseUrl: baseUrl.trim() || "",
      apiKey: apiKey.trim(),
    };
    try {
      await checkReady(session);
      onConnect(session);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not reach the API. Is Compose running?";
      setError(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="relative flex min-h-screen flex-col justify-center px-6 py-16 md:px-12">
      <div className="mx-auto w-full max-w-xl">
        <p className="font-[family-name:var(--font-display)] text-6xl leading-none tracking-tight md:text-7xl">
          AgentOS
        </p>
        <p className="mt-5 max-w-md text-lg text-[var(--black-4)]">
          Register agents, queue durable tasks, and watch the worker recover after a crash.
        </p>

        <form
          onSubmit={handleSubmit}
          className="mt-12 space-y-5 border border-[var(--black-10)] bg-[var(--beige-4)] p-6"
        >
          <label className="block">
            <span className="text-sm font-medium text-[var(--black-3)]">API base URL</span>
            <input
              className="mt-2 w-full border border-[var(--black-10)] bg-[var(--beige-5)] px-3 py-2 outline-none focus:border-[var(--cta)]"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="leave empty to use this origin (Vite proxy)"
              autoComplete="off"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-[var(--black-3)]">API key</span>
            <input
              className="mt-2 w-full border border-[var(--black-10)] bg-[var(--beige-5)] px-3 py-2 font-[family-name:var(--font-mono)] text-sm outline-none focus:border-[var(--cta)]"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              required
              autoComplete="off"
            />
          </label>
          {error ? (
            <p className="text-sm text-[var(--sweet-dark)]" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={pending || !apiKey.trim()}
            className="bg-[var(--cta)] px-5 py-2.5 font-semibold text-white transition enabled:hover:brightness-95 disabled:opacity-50"
          >
            {pending ? "Connecting…" : "Continue"}
          </button>
        </form>
      </div>
    </main>
  );
}
