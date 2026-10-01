"""Application-specific exceptions for NovaMart support."""


class NovaMartError(Exception):
    """Base exception for NovaMart support errors."""


class ConfigurationError(NovaMartError):
    """Raised when required application configuration is invalid."""


class WorkflowNotFoundError(NovaMartError):
    """Raised when a workflow session cannot be found."""


class WorkflowAlreadyExistsError(NovaMartError):
    """Raised when attempting to create an existing workflow."""


class ConcurrencyConflictError(NovaMartError):
    """Raised when optimistic locking detects a stale workflow version."""


class CustomerNotFoundError(NovaMartError):
    """Raised when a requested customer does not exist."""


class OrderNotFoundError(NovaMartError):
    """Raised when a requested order does not exist."""


class PolicyRetrievalError(NovaMartError):
    """Raised when policy evidence cannot be retrieved."""

class WorkflowTransitionError(NovaMartError):
    """Raised when a workflow attempts an invalid state or routing transition."""

class AgentExecutionError(NovaMartError):
    """Raised when typed multi-agent runtime execution fails."""
