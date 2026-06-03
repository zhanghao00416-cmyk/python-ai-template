from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


class DIContainer:
    __slots__ = ("_factories", "_instances", "_overrides", "_non_singleton")

    def __init__(self) -> None:
        self._factories: dict[type, Callable[[], Any]] = {}
        self._instances: dict[type, Any] = {}
        self._overrides: dict[type, Callable[[], Any]] = {}
        self._non_singleton: set[type] = set()

    def register(self, cls: type, factory: Callable[[], Any], singleton: bool = True) -> None:
        self._factories[cls] = factory
        if not singleton:
            self._non_singleton.add(cls)
        else:
            self._non_singleton.discard(cls)
        self._instances.pop(cls, None)

    def resolve(self, cls: type[T]) -> T:
        factory = self._overrides.get(cls) or self._factories.get(cls)
        if factory is None:
            raise KeyError(f"No factory registered for {cls.__name__}")
        if cls in self._instances:
            return self._instances[cls]
        instance = factory()
        if cls in self._factories and cls not in self._overrides:
            is_singleton = cls not in self._non_singleton
            if is_singleton:
                self._instances[cls] = instance
        return instance

    def override(self, cls: type, factory: Callable[[], Any]) -> None:
        self._overrides[cls] = factory
        self._instances.pop(cls, None)

    def reset(self, cls: type | None = None) -> None:
        if cls is None:
            self._overrides.clear()
            self._instances.clear()
        else:
            self._overrides.pop(cls, None)
            self._instances.pop(cls, None)

    def cleanup(self) -> None:
        self._instances.clear()


container = DIContainer()