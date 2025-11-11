"""Backward-compatible entrypoint for the UNS metadata sync service."""

from uns_metadata_sync import main as run_service


if __name__ == "__main__":
    run_service()
