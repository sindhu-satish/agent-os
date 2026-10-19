const TERMINAL = new Set(["succeeded", "failed", "cancelled", "dead_letter"]);

export function isTerminal(status: string): boolean {
  return TERMINAL.has(status);
}

export function statusChipStyle(status: string): { background: string; color: string } {
  switch (status) {
    case "succeeded":
      return { background: "var(--bitter-light)", color: "var(--bitter-dark)" };
    case "running":
    case "leased":
      return { background: "var(--mint-light)", color: "var(--mint-dark)" };
    case "queued":
    case "pending":
      return { background: "var(--mineral-light)", color: "var(--mineral-dark)" };
    case "failed":
    case "dead_letter":
      return { background: "var(--sweet-light)", color: "var(--sweet-dark)" };
    case "recovering":
    case "cancel_requested":
    case "cancelled":
      return { background: "var(--sour-light)", color: "var(--sour-dark)" };
    default:
      return { background: "var(--beige-2)", color: "var(--black-3)" };
  }
}

export function stepKindStyle(kind: string): { background: string; color: string } {
  if (kind === "tool") {
    return { background: "var(--almond-light)", color: "var(--almond-dark)" };
  }
  if (kind === "model") {
    return { background: "var(--olive-light)", color: "var(--olive-dark)" };
  }
  return { background: "var(--beige-2)", color: "var(--black-3)" };
}
