"""Custom exceptions for the codexy project."""


class codexyError(Exception):
    """Base exception for codexy errors."""

    pass


class ToolError(codexyError):
    """Exception related to tool execution."""

    pass


class ConfigError(codexyError):
    """Exception related to configuration issues."""

    pass
