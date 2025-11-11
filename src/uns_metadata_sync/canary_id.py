"""Helpers for deriving Canary tag identifiers from UNS paths."""

from __future__ import annotations

import binascii
import logging
from dataclasses import dataclass
from typing import Dict, Tuple

LOGGER = logging.getLogger(__name__)

_ALLOWED_STATIC_CHARS = frozenset("._-")
_ALLOWED_SPACE = " "


def _is_allowed_char(char: str) -> bool:
    """Return True when character may appear in Canary identifiers without escaping."""

    if char.isalnum():
        return True
    if char == _ALLOWED_SPACE:
        return True
    if char in _ALLOWED_STATIC_CHARS:
        return True
    return False


_ESCAPE_PREFIX = "_x"


@dataclass(frozen=True)
class CanaryId:
    """Represents the derived Canary identifier and optional checksum."""

    tag: str
    checksum: str | None = None


class CanaryIdGenerator:
    """Convert UNS paths into Canary tag identifiers with collision tracking."""

    def __init__(self) -> None:
        self._known_ids: Dict[str, str] = {}
        self._collisions_total = 0
        self._escapes_total = 0

    @property
    def collisions_total(self) -> int:
        """Number of times distinct UNS paths generated the same Canary id."""

        return self._collisions_total

    @property
    def escapes_total(self) -> int:
        """Number of segments that required escaping."""

        return self._escapes_total

    def generate(self, uns_path: str, *, include_checksum: bool = False) -> CanaryId:
        """Return the derived `CanaryId` for `uns_path`.

        Trims each segment (preserving internal whitespace) and escapes characters
        that are incompatible with Canary identifiers. Collision attempts are
        counted and logged at warning level.
        """

        if not isinstance(uns_path, str):
            raise TypeError("uns_path must be a string")

        trimmed = uns_path.strip()
        if not trimmed:
            raise ValueError("uns_path cannot be blank")

        raw_segments = [segment for segment in trimmed.strip("/").split("/") if segment]
        if not raw_segments:
            raise ValueError("uns_path did not contain any path segments")

        normalised_segments: list[str] = []
        for segment in raw_segments:
            trimmed_segment = segment.strip()
            if not trimmed_segment:
                raise ValueError("uns_path contains a segment with only whitespace")
            normalised_segments.append(trimmed_segment)

        escaped_segments = [
            self._escape_segment(segment) for segment in normalised_segments
        ]
        canary_id = ".".join(escaped for escaped, _ in escaped_segments)

        for original, (_, replacements) in zip(normalised_segments, escaped_segments):
            if replacements:
                self._escapes_total += 1
                LOGGER.info(
                    "canary_id: escaped %d character(s) in segment '%s'",
                    replacements,
                    original,
                )

        self._record_generation(canary_id, trimmed)

        checksum_value = (
            format(binascii.crc32(canary_id.encode("utf-8")) & 0xFFFFFFFF, "08x")
            if include_checksum
            else None
        )
        return CanaryId(tag=canary_id, checksum=checksum_value)

    def _escape_segment(self, segment: str) -> Tuple[str, int]:
        """Return escaped segment and number of characters replaced."""

        if not segment:
            raise ValueError("uns_path contains a segment with only whitespace")

        escaped: list[str] = []
        replacements = 0
        for char in segment:
            if _is_allowed_char(char):
                escaped.append(char)
            elif char.isspace():
                replacements += 1
                escaped.append(_ALLOWED_SPACE)
            else:
                replacements += 1
                escaped.append(f"{_ESCAPE_PREFIX}{ord(char):04X}")
        return "".join(escaped), replacements

    def _record_generation(self, canary_id: str, source_path: str) -> None:
        """Track generated ids and detect collisions for metric purposes."""

        existing = self._known_ids.get(canary_id)
        if existing is None:
            self._known_ids[canary_id] = source_path
            return
        if existing != source_path:
            self._collisions_total += 1
            LOGGER.warning(
                "canary_id collision: '%s' already mapped from '%s', incoming '%s'",
                canary_id,
                existing,
                source_path,
            )


_default_generator = CanaryIdGenerator()


def generate_canary_id(uns_path: str) -> str:
    """Convenience wrapper returning only the Canary id string."""

    return _default_generator.generate(uns_path).tag
