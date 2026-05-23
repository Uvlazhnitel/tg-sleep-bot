class MissingConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


class UpstreamServiceError(RuntimeError):
    """Raised when the upstream OpenAI request fails or returns invalid output."""


class MemoryNotFoundError(RuntimeError):
    """Raised when a requested memory record is not found."""
