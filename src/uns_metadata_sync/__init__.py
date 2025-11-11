"""Metadata synchronization service for UNS Sparkplug B payloads."""

from .canary_id import CanaryIdGenerator, generate_canary_id


def main() -> None:
    """Entrypoint proxy that defers importing the service until needed."""

    from .service import main as _service_main

    _service_main()


__all__ = ["main", "generate_canary_id", "CanaryIdGenerator"]
