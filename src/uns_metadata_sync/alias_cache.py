"""Helpers for serializing and persisting Sparkplug alias metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Optional, Tuple

AliasKey = Tuple[str, str, Optional[str]]
AliasInfo = Dict[str, object]
AliasMap = Dict[int, AliasInfo]
AliasRegistry = MutableMapping[AliasKey, AliasMap]


def serialize_alias_maps(
    alias_maps: Mapping[AliasKey, AliasMap],
) -> Dict[str, Dict[str, AliasInfo]]:
    """Convert the nested alias mapping into a JSON-serialisable dictionary."""
    serialised: Dict[str, Dict[str, AliasInfo]] = {}
    for (group, edge_node, device), entries in alias_maps.items():
        device_token = "" if device is None else device
        key = f"{group}|{edge_node}|{device_token}"
        serialised[key] = {str(alias): info for alias, info in entries.items()}
    return serialised


def deserialize_alias_maps(
    data: Mapping[str, Mapping[str, AliasInfo]],
) -> Dict[AliasKey, AliasMap]:
    """Reconstruct the nested alias mapping from its serialised form."""
    alias_maps: Dict[AliasKey, AliasMap] = {}
    for composite_key, entries in data.items():
        group, edge_node, device_token = composite_key.split("|", 2)
        device: Optional[str] = device_token or None
        alias_maps[(group, edge_node, device)] = {
            int(alias): info for alias, info in entries.items()
        }
    return alias_maps


def load_alias_cache(path: Path) -> Dict[AliasKey, AliasMap]:
    """Load alias metadata from `path` if it exists."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return deserialize_alias_maps(data)


def save_alias_cache(path: Path, alias_maps: Mapping[AliasKey, AliasMap]) -> None:
    """Persist `alias_maps` to disk using UTF-8 JSON."""
    payload = json.dumps(
        serialize_alias_maps(alias_maps),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(payload + "\n", encoding="utf-8")
