"""Status values stored on tasks, executions, and steps."""

EXECUTION_STATUSES = (
    "pending",
    "queued",
    "leased",
    "running",
    "cancel_requested",
    "recovering",
    "succeeded",
    "failed",
    "cancelled",
    "dead_letter",
)

STEP_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
STEP_KINDS = ("model", "tool", "system")
AGENT_STATUSES = ("active", "disabled")
MEMORY_KINDS = ("working", "persistent")


def sql_in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"
