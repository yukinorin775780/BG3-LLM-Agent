from __future__ import annotations

from typing import Dict, Optional

from core.actors.contracts import ActorRuntime
from core.actors.runtime import TemplateActorRuntime


class ActorRegistry:
    def __init__(self) -> None:
        self._runtimes: Dict[str, ActorRuntime] = {}

    def register(self, actor_id: str, runtime: ActorRuntime) -> None:
        self._runtimes[str(actor_id or "").strip().lower()] = runtime

    def try_get(self, actor_id: str) -> Optional[ActorRuntime]:
        return self._runtimes.get(str(actor_id or "").strip().lower())

    def get(self, actor_id: str) -> ActorRuntime:
        normalized_actor_id = str(actor_id or "").strip().lower()
        runtime = self._runtimes.get(normalized_actor_id)
        if runtime is None:
            raise KeyError(f"Unknown actor runtime: {normalized_actor_id}")
        return runtime


_DEFAULT_ACTOR_REGISTRY: Optional[ActorRegistry] = None


def get_default_actor_registry() -> ActorRegistry:
    global _DEFAULT_ACTOR_REGISTRY
    if _DEFAULT_ACTOR_REGISTRY is None:
        registry = ActorRegistry()
        # Phase 3 V1: only shadowheart is upgraded to ActorRuntime.
        registry.register("shadowheart", TemplateActorRuntime("shadowheart"))
        _DEFAULT_ACTOR_REGISTRY = registry
    return _DEFAULT_ACTOR_REGISTRY
