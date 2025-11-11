"""Command line interface for migration runner."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from .runner import apply_migrations, rollback_last


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UNS metadata migration runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply all pending migrations")
    apply_parser.add_argument(
        "--conninfo", help="psycopg connection string", default=None
    )
    apply_parser.add_argument(
        "--target-version",
        help="Apply migrations up to and including this version",
        default=None,
    )
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migrations that would run without executing them",
    )

    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback the most recent migration"
    )
    rollback_parser.add_argument(
        "--conninfo", help="psycopg connection string", default=None
    )
    rollback_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which migration would be rolled back",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "apply":
        executed = apply_migrations(
            conninfo=args.conninfo,
            target_version=args.target_version,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            for migration in executed:
                print(
                    f"DRY-RUN would apply migration {migration.version}_{migration.name}"
                )
        else:
            for migration in executed:
                print(f"Applied migration {migration.version}_{migration.name}")
        return 0

    if args.command == "rollback":
        migration = rollback_last(conninfo=args.conninfo, dry_run=args.dry_run)
        if migration is None:
            print("No migrations to rollback")
            return 0
        if args.dry_run:
            print(
                f"DRY-RUN would rollback migration {migration.version}_{migration.name}"
            )
        else:
            print(f"Rolled back migration {migration.version}_{migration.name}")
        return 0

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
