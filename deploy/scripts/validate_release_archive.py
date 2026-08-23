#!/usr/bin/env python3
"""Validate a release archive before privileged extraction."""

from __future__ import annotations

from pathlib import PurePosixPath
import sys
import tarfile


MAX_MEMBERS = 20_000
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


def validate_archive(path: str) -> None:
    member_count = 0
    unpacked_bytes = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive:
                member_count += 1
                unpacked_bytes += member.size
                name = PurePosixPath(member.name)
                if (
                    member_count > MAX_MEMBERS
                    or unpacked_bytes > MAX_UNPACKED_BYTES
                    or name.is_absolute()
                    or ".." in name.parts
                    or not name.parts
                    or name.parts[0] != "release"
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError
    except (OSError, tarfile.TarError, ValueError) as error:
        raise SystemExit("The release archive structure is unsafe.") from error
    if member_count == 0:
        raise SystemExit("The release archive is empty.")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_release_archive.py ARCHIVE")
    validate_archive(sys.argv[1])


if __name__ == "__main__":
    main()
