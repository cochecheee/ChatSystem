"""Artifact profile loader.

A profile defines which workflow artifact names a `SecurityProcessor` should
treat as security findings. Profiles live as YAML files under `mcp/config/profiles/`.
This indirection lets one chat-system instance serve repos with different CI
conventions (Java Spring vs Python Bandit vs Node ESLint, etc.) without code
changes.

Day 1 scope: load a single profile from disk based on the `ARTIFACT_PROFILE`
env var. Day 2 (multi-project) will look up the profile per `Project` row.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_PROFILES_DIR = Path(__file__).resolve().parents[2] / "config" / "profiles"
_DEFAULT_PROFILE = "github-actions-default"


@dataclass(frozen=True)
class ArtifactProfile:
    name: str
    exact_names: frozenset[str]
    prefixes: tuple[str, ...]

    def matches(self, artifact_name: str) -> bool:
        if artifact_name in self.exact_names:
            return True
        return any(artifact_name.startswith(p) for p in self.prefixes)


@lru_cache(maxsize=None)
def load_profile(name: str | None = None) -> ArtifactProfile:
    profile_name = name or os.getenv("ARTIFACT_PROFILE", _DEFAULT_PROFILE)
    path = _PROFILES_DIR / f"{profile_name}.yml"

    if not path.exists():
        log.warning(
            "Artifact profile %r not found at %s — falling back to %s",
            profile_name, path, _DEFAULT_PROFILE,
        )
        path = _PROFILES_DIR / f"{_DEFAULT_PROFILE}.yml"

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return ArtifactProfile(
        name=data.get("name", profile_name),
        exact_names=frozenset(data.get("exact_names", [])),
        prefixes=tuple(data.get("prefixes", [])),
    )
