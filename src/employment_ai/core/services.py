from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ServiceEntry:
    capability: str
    provider_id: str
    service: Any


class ServiceContainer:
    def __init__(self) -> None:
        self._services: dict[str, ServiceEntry] = {}

    def register(self, capability: str, provider_id: str, service: Any) -> None:
        if capability in self._services:
            owner = self._services[capability].provider_id
            raise ValueError(f"capability {capability} already provided by {owner}")
        self._services[capability] = ServiceEntry(capability, provider_id, service)

    def get(self, capability: str) -> Any:
        try:
            return self._services[capability].service
        except KeyError as exc:
            raise KeyError(f"capability is not available: {capability}") from exc

    def has(self, capability: str) -> bool:
        return capability in self._services

    def unregister_provider(self, provider_id: str) -> None:
        for capability in [
            key for key, entry in self._services.items() if entry.provider_id == provider_id
        ]:
            self._services.pop(capability, None)

    def snapshot(self) -> list[dict[str, str]]:
        return [
            {"capability": item.capability, "provider_id": item.provider_id}
            for item in sorted(self._services.values(), key=lambda value: value.capability)
        ]
