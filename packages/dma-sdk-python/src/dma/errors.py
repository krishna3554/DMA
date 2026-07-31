"""Errors raised by the DMA SDK."""

from __future__ import annotations


class DMAError(Exception):
    """Base class for all DMA SDK errors."""


class ValidationError(DMAError):
    """The client rejected invalid input before making a network request."""


class DMAConnectionError(DMAError):
    """The DMA service could not be reached within the configured timeout."""


class DMAApiError(DMAError):
    """The DMA service returned an unsuccessful response."""

    def __init__(self, status_code: int, message: str, *, code: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class AuthenticationError(DMAApiError):
    """The supplied API key was rejected by the DMA service."""
