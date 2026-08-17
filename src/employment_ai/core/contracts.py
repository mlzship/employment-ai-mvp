from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from employment_ai.core.context import AppContext


PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class PluginState(StrEnum):
    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    version: str
    name: str
    description: str
    provides: tuple[str, ...]
    requires: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    config_schema: dict[str, Any] = field(default_factory=dict)
    events_in: tuple[str, ...] = ()
    events_out: tuple[str, ...] = ()
    cleanup_strategy: str = "unregister services and release local resources"

    def validate(self) -> None:
        if not PLUGIN_ID_RE.match(self.id):
            raise ValueError(f"invalid plugin id: {self.id}")
        if not SEMVER_RE.match(self.version):
            raise ValueError(f"invalid plugin version: {self.version}")
        if not self.name.strip():
            raise ValueError("plugin name is required")
        if not self.provides:
            raise ValueError(f"plugin {self.id} must provide at least one capability")
        if len(set(self.provides)) != len(self.provides):
            raise ValueError(f"plugin {self.id} has duplicate capabilities")
        if not self.cleanup_strategy.strip():
            raise ValueError(f"plugin {self.id} must declare cleanup strategy")


class Plugin(ABC):
    manifest: PluginManifest

    @abstractmethod
    def install(self, context: "AppContext") -> None:
        """Register services but do not start background work."""

    def start(self, context: "AppContext") -> None:
        """Enter the enabled state."""
        return None

    def health(self, context: "AppContext") -> dict[str, Any]:
        return {"status": "ok"}

    def stop(self, context: "AppContext") -> None:
        """Release local resources. Service removal is handled by the registry."""
        return None
