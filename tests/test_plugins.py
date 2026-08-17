from pathlib import Path

import pytest

from employment_ai.core.context import AppContext
from employment_ai.core.database import Database
from employment_ai.core.events import EventBus
from employment_ai.core.registry import PluginRegistry
from employment_ai.core.services import ServiceContainer
from employment_ai.plugins.catalog import built_in_plugins
from employment_ai.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def _registry(tmp_path: Path) -> PluginRegistry:
    settings = Settings(
        database_path=tmp_path / "plugins.db",
        ontology_path=ROOT / "data/ontology/employment_ontology.json",
        auto_seed=False,
    )
    database = Database(settings.database_path)
    database.init_schema()
    context = AppContext(settings, database, EventBus(), ServiceContainer())
    registry = PluginRegistry(context)
    for plugin in built_in_plugins():
        registry.register(plugin)
    registry.enable_all()
    return registry


def test_registry_resolves_ontology_before_excel(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    order = registry.resolve_order()

    assert order.index("data-quality") < order.index("semantic-ontology")
    assert order.index("semantic-ontology") < order.index("excel-source")
    assert all(item["state"] == "enabled" for item in registry.status())


def test_registry_blocks_disabling_plugin_with_dependents(tmp_path: Path) -> None:
    registry = _registry(tmp_path)

    with pytest.raises(ValueError, match="enabled dependents"):
        registry.disable("data-quality", actor="tester")

    registry.disable("match-export", actor="tester")
    status = {item["id"]: item["state"] for item in registry.status()}
    assert status["match-export"] == "disabled"
