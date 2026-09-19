"""Fireflyer — tooling for a self-hosted, browser-editable Firefly blog."""

from __future__ import annotations

try:
    from importlib.metadata import version as _version

    __version__ = _version("fireflyer")
except Exception:  # not installed, e.g. running straight from a checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
