export type Agent = {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: string;
  current_version_id: string | null;
  max_concurrency: number;
};

export type Task = {
  id: string;
  agent_id: string;
  status: string;
  idempotency_key: string;
  priority: number;
  input: Record<string, unknown>;
  execution_id: string | null;
};

export type Step = {
  sequence: number;
  kind: string;
  status: string;
  name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
};

export type Execution = {
  id: string;
  task_id: string;
  status: string;
  attempt: number;
  fencing_token: number;
  result: Record<string, unknown> | null;
  error: string | null;
  steps: Step[];
};

export type Session = {
  apiKey: string;
  baseUrl: string;
};

const SESSION_KEY = "agentos.session";

export function loadSession(): Session | null {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function saveSession(session: Session): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  session: Session,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${session.apiKey}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const url = `${session.baseUrl.replace(/\/$/, "")}${path}`;
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail != null) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function checkReady(session: Session): Promise<void> {
  const url = `${session.baseUrl.replace(/\/$/, "")}/ready`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(response.status, "API is not ready");
  }
}

export function listAgents(session: Session): Promise<Agent[]> {
  return request(session, "/v1/agents");
}

export function createAgent(
  session: Session,
  body: {
    name: string;
    slug: string;
    tool_names: string[];
    description?: string;
    system_prompt?: string;
  },
): Promise<Agent> {
  return request(session, "/v1/agents", {
    method: "POST",
    body: JSON.stringify({
      name: body.name,
      slug: body.slug,
      description: body.description ?? "",
      tool_names: body.tool_names,
      system_prompt: body.system_prompt ?? "",
    }),
  });
}

export function createTask(
  session: Session,
  body: {
    agent_id: string;
    input: Record<string, unknown>;
    idempotency_key: string;
  },
): Promise<Task> {
  return request(session, "/v1/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelTask(session: Session, taskId: string): Promise<Task> {
  return request(session, `/v1/tasks/${taskId}/cancel`, { method: "POST" });
}

export function getExecution(session: Session, executionId: string): Promise<Execution> {
  return request(session, `/v1/executions/${executionId}`);
}

export function createDemoRecovery(
  session: Session,
  agentId: string,
): Promise<{ execution_id: string }> {
  return request(session, "/v1/demo/recoveries", {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId }),
  });
}
