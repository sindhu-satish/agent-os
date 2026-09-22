"""Domain errors raised by repositories and the execution engine."""


class AgentOSError(Exception):
    """Base error for expected domain failures."""


class NotFound(AgentOSError):
    """The requested tenant-scoped record does not exist."""


class IdempotencyConflict(AgentOSError):
    """The idempotency key was reused with a different payload."""


class LostLease(AgentOSError):
    """The worker no longer owns the execution fence."""
