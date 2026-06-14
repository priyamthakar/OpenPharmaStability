"""Shelf-life engine: orchestrate data -> fit -> pool -> select -> bound -> crossing.

The v0.2.0 multi-attribute entry point :func:`analyze_many` and the
limiting-attribute decision function :func:`select_limiting` are
re-exported here so callers can write::

    from openpharmastability.shelf_life import analyze_many, select_limiting
"""
from .limiting import select_limiting
from .multi_engine import analyze_many

__all__ = ["analyze_many", "select_limiting"]
