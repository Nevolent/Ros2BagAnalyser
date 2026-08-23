#!/usr/bin/env python3
"""Validate that a wheelhouse contains exactly its checksummed regular files."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys


CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.+-]{0,254})$")


def validate_wheelhouse(path: Path) -> None:
    try:
        if path.is_symlink() or not path.is_dir():
            raise OSError
        manifest = path / "SHA256SUMS"
        if manifest.is_symlink() or not manifest.is_file():
            raise OSError
        payload = manifest.read_bytes()
        if len(payload) > 1024 * 1024:
            raise OSError
        lines = payload.decode("ascii").splitlines()
        expected: dict[str, str] = {}
        for line in lines:
            match = CHECKSUM_LINE.fullmatch(line)
            if match is None or match.group(2) in expected:
                raise ValueError
            expected[match.group(2)] = match.group(1)
        actual = {
            item.name
            for item in path.iterdir()
            if item.name != "SHA256SUMS" and item.is_file() and not item.is_symlink()
        }
        all_entries = {item.name for item in path.iterdir()}
        if not expected or actual != set(expected) or all_entries != actual | {"SHA256SUMS"}:
            raise ValueError
        for name, expected_digest in expected.items():
            digest = hashlib.sha256((path / name).read_bytes()).hexdigest()
            if digest != expected_digest:
                raise ValueError
    except (OSError, UnicodeError, ValueError) as error:
        raise SystemExit("The wheelhouse content or checksum identity is invalid.") from error


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_wheelhouse.py WHEELHOUSE")
    validate_wheelhouse(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
