from __future__ import annotations

from collections import OrderedDict
from typing import Any

from employment_ai.core.context import AppContext
from employment_ai.core.contracts import Plugin, PluginState


class PluginRegistry:
    def __init__(self, context: AppContext) -> None:
        self.context = context
        self._plugins: "OrderedDict[str, Plugin]" = OrderedDict()
        self._states: dict[str, PluginState] = {}
        self._errors: dict[str, str] = {}
        self._capability_owner: dict[str, str] = {}

    def register(self, plugin: Plugin) -> None:
        plugin.manifest.validate()
        plugin_id = plugin.manifest.id
        if plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin id: {plugin_id}")
        for capability in plugin.manifest.provides:
            if capability in self._capability_owner:
                owner = self._capability_owner[capability]
                raise ValueError(f"capability {capability} already declared by {owner}")
            self._capability_owner[capability] = plugin_id
        self._plugins[plugin_id] = plugin
        self._states[plugin_id] = PluginState.REGISTERED

    def _plugin_dependencies(self, plugin_id: str) -> set[str]:
        dependencies: set[str] = set()
        for capability in self._plugins[plugin_id].manifest.requires:
            provider = self._capability_owner.get(capability)
            if provider is None:
                raise ValueError(f"{plugin_id} requires missing capability {capability}")
            dependencies.add(provider)
        return dependencies

    def resolve_order(self) -> list[str]:
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def visit(plugin_id: str) -> None:
            if plugin_id in visited:
                return
            if plugin_id in visiting:
                raise ValueError(f"plugin dependency cycle detected at {plugin_id}")
            visiting.add(plugin_id)
            for dependency in sorted(self._plugin_dependencies(plugin_id)):
                visit(dependency)
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            order.append(plugin_id)

        for plugin_id in self._plugins:
            visit(plugin_id)
        return order

    def enable_all(self, disabled: tuple[str, ...] = ()) -> None:
        disabled_set = set(disabled)
        unknown = disabled_set.difference(self._plugins)
        if unknown:
            raise ValueError(f"unknown disabled plugins: {', '.join(sorted(unknown))}")
        for plugin_id in self.resolve_order():
            if plugin_id in disabled_set:
                self._states[plugin_id] = PluginState.DISABLED
                continue
            unavailable = [
                dependency
                for dependency in self._plugin_dependencies(plugin_id)
                if self._states[dependency] not in {PluginState.ENABLED, PluginState.DEGRADED}
            ]
            if unavailable:
                self._states[plugin_id] = PluginState.DISABLED
                self._errors[plugin_id] = "startup dependency disabled: " + ", ".join(
                    sorted(unavailable)
                )
                continue
            self.enable(plugin_id, actor="system")

    def enable(self, plugin_id: str, actor: str) -> None:
        if plugin_id not in self._plugins:
            raise KeyError(plugin_id)
        if self._states[plugin_id] in {PluginState.ENABLED, PluginState.DEGRADED}:
            return
        for dependency in self._plugin_dependencies(plugin_id):
            if self._states[dependency] not in {PluginState.ENABLED, PluginState.DEGRADED}:
                self.enable(dependency, actor=actor)
        plugin = self._plugins[plugin_id]
        try:
            plugin.install(self.context)
            plugin.start(self.context)
            health = plugin.health(self.context)
            self._states[plugin_id] = (
                PluginState.ENABLED if health.get("status") == "ok" else PluginState.DEGRADED
            )
            self._errors.pop(plugin_id, None)
            self.context.audit(
                "plugin.enabled",
                actor,
                {"plugin_id": plugin_id, "version": plugin.manifest.version},
            )
        except Exception as exc:
            self.context.services.unregister_provider(plugin_id)
            self._states[plugin_id] = PluginState.FAILED
            self._errors[plugin_id] = str(exc)
            raise

    def disable(self, plugin_id: str, actor: str) -> None:
        if plugin_id not in self._plugins:
            raise KeyError(plugin_id)
        dependents = [
            candidate
            for candidate in self._plugins
            if plugin_id in self._plugin_dependencies(candidate)
            and self._states[candidate] in {PluginState.ENABLED, PluginState.DEGRADED}
        ]
        if dependents:
            raise ValueError(
                f"cannot disable {plugin_id}; enabled dependents: {', '.join(dependents)}"
            )
        plugin = self._plugins[plugin_id]
        if self._states[plugin_id] in {PluginState.ENABLED, PluginState.DEGRADED}:
            plugin.stop(self.context)
        self.context.services.unregister_provider(plugin_id)
        self._states[plugin_id] = PluginState.DISABLED
        self.context.audit(
            "plugin.disabled",
            actor,
            {"plugin_id": plugin_id, "cleanup": plugin.manifest.cleanup_strategy},
        )

    def shutdown(self) -> None:
        for plugin_id in reversed(self.resolve_order()):
            if self._states.get(plugin_id) in {PluginState.ENABLED, PluginState.DEGRADED}:
                self._plugins[plugin_id].stop(self.context)
                self.context.services.unregister_provider(plugin_id)
                self._states[plugin_id] = PluginState.DISABLED

    def status(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for plugin_id, plugin in self._plugins.items():
            manifest = plugin.manifest
            result.append(
                {
                    "id": plugin_id,
                    "name": manifest.name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "state": self._states[plugin_id].value,
                    "provides": list(manifest.provides),
                    "requires": list(manifest.requires),
                    "permissions": list(manifest.permissions),
                    "cleanup_strategy": manifest.cleanup_strategy,
                    "error": self._errors.get(plugin_id),
                }
            )
        return result
