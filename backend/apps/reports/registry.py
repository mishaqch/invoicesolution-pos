"""Report registry — maps name → Report class.

Every report module imports `register` and decorates its class. The
view layer looks up by name from a single source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Report


_REGISTRY: dict[str, type["Report"]] = {}


def register(cls: type["Report"]) -> type["Report"]:
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must define `name` to register")
    if cls.name in _REGISTRY:
        raise ValueError(f"Report {cls.name!r} already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> type["Report"]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"No report named {name!r}") from exc


def all_reports() -> dict[str, type["Report"]]:
    return dict(_REGISTRY)


def names() -> list[str]:
    return sorted(_REGISTRY.keys())
