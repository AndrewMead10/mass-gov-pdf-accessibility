"""Pipeline discovery utilities."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Iterable, List, Type

from .base import BasePipeline

_PIPELINE_CACHE: Dict[str, Type[BasePipeline]] = {}
_INSTANCE_CACHE: Dict[str, BasePipeline] = {}


def _iter_module_names() -> Iterable[str]:
    package = __name__
    for module_info in pkgutil.iter_modules(__path__, prefix=f"{package}."):
        name = module_info.name
        if name.endswith((".base", ".helpers", ".manager")):
            continue
        yield name


def _load_pipeline_classes() -> None:
    if _PIPELINE_CACHE:
        return
    for module_name in _iter_module_names():
        module = importlib.import_module(module_name)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BasePipeline) and attr is not BasePipeline:
                instance = attr()
                _PIPELINE_CACHE[instance.slug] = attr
                _INSTANCE_CACHE[instance.slug] = instance


def registered_slugs() -> List[str]:
    """Return the list of pipeline slugs currently registered."""
    _load_pipeline_classes()
    return sorted(_PIPELINE_CACHE.keys())


def get_pipeline(slug: str) -> BasePipeline:
    """Return a singleton instance for the requested pipeline."""
    _load_pipeline_classes()
    try:
        return _INSTANCE_CACHE[slug]
    except KeyError as exc:
        raise KeyError(f"Pipeline not found: {slug}") from exc


def iter_pipelines() -> Iterable[BasePipeline]:
    """Yield instantiated pipelines."""
    _load_pipeline_classes()
    for pipeline in _INSTANCE_CACHE.values():
        yield pipeline


__all__ = ["BasePipeline", "get_pipeline", "iter_pipelines", "registered_slugs"]
