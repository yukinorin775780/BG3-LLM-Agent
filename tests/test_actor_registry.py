import pytest

from core.actors.registry import ActorRegistry


class DummyRuntime:
    pass


def test_actor_registry_returns_registered_runtime():
    registry = ActorRegistry()
    runtime = DummyRuntime()

    registry.register("shadowheart", runtime)

    assert registry.get("shadowheart") is runtime


def test_actor_registry_raises_for_unknown_actor():
    registry = ActorRegistry()

    with pytest.raises(KeyError):
        registry.get("astarion")
