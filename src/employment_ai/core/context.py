from __future__ import annotations

from dataclasses import dataclass

from employment_ai.core.database import Database
from employment_ai.core.events import EventBus
from employment_ai.core.services import ServiceContainer
from employment_ai.settings import Settings


@dataclass(slots=True)
class AppContext:
    settings: Settings
    db: Database
    events: EventBus
    services: ServiceContainer

    def audit(self, action: str, actor: str, details: dict[str, object]) -> None:
        self.db.add_audit(action=action, actor=actor, details=details)
