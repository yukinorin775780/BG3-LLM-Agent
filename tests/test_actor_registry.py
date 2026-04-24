import pytest
import yaml

import core.actors.registry as registry_module
from core.actors.registry import ActorRegistry, load_runtime_actor_ids


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


def test_default_registry_enables_astarion_runtime(monkeypatch):
    monkeypatch.setattr(registry_module, "_DEFAULT_ACTOR_REGISTRY", None)
    registry = registry_module.get_default_actor_registry()

    assert registry.try_get("astarion") is not None


def test_default_registry_enables_laezel_runtime(monkeypatch):
    monkeypatch.setattr(registry_module, "_DEFAULT_ACTOR_REGISTRY", None)
    registry = registry_module.get_default_actor_registry()

    assert registry.try_get("laezel") is not None


def test_runtime_actor_ids_are_loaded_from_yaml_config(tmp_path):
    config_path = tmp_path / "runtime_actor_registry.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "runtime_enabled_actors": [
                    "Shadowheart",
                    "astarion",
                    "Astarion",
                    "Laezel",
                    "   ",
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    actor_ids = load_runtime_actor_ids(config_path)

    assert actor_ids == ("shadowheart", "astarion", "laezel")


def test_default_runtime_actor_config_file_exists():
    config_path = registry_module._default_runtime_registry_config_path()
    actor_ids = load_runtime_actor_ids(config_path)

    assert "shadowheart" in actor_ids
    assert "astarion" in actor_ids
    assert "laezel" in actor_ids


def test_default_registry_uses_runtime_actor_ids_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "runtime_actor_registry.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "runtime_enabled_actors": [
                    "laezel",
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        registry_module,
        "_default_runtime_registry_config_path",
        lambda: config_path,
    )
    monkeypatch.setattr(registry_module, "_DEFAULT_ACTOR_REGISTRY", None)

    registry = registry_module.get_default_actor_registry()

    assert registry.try_get("laezel") is not None
    assert registry.try_get("shadowheart") is None
