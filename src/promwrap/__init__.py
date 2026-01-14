"""Minimal Prometheus HTTP API wrapper (stdlib-only).

This package is intentionally dependency-light to support the "direct HTTP API" approach.
"""

from .client import PromClient, PromwrapConfig, PromwrapError

__all__ = ["PromClient", "PromwrapConfig", "PromwrapError"]
