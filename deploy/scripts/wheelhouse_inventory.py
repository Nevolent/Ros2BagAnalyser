#!/usr/bin/env python3
from __future__ import annotations

from email.parser import BytesParser
import json
from pathlib import Path
import platform
import re
import sys
import zipfile


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: wheelhouse_inventory.py WHEELHOUSE OUTPUT SOURCE_REPOSITORY_LABEL"
        )
    wheelhouse = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).absolute()
    if output.parent != wheelhouse:
        raise SystemExit("The licence inventory must remain beside the wheelhouse.")
    source_repository_label = sys.argv[3]
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", source_repository_label) is None:
        raise SystemExit("The sanitized source-repository label is invalid.")
    packages: list[dict[str, object]] = []
    for wheel in sorted(wheelhouse.glob("*.whl"), key=lambda path: path.name):
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA") and name.count("/") == 1
            ]
            if len(metadata_names) != 1:
                raise SystemExit("A wheel has an ambiguous metadata record.")
            message = BytesParser().parsebytes(archive.read(metadata_names[0]))
        packages.append(
            {
                "wheel": wheel.name,
                "name": message.get("Name", ""),
                "version": message.get("Version", ""),
                "license_expression": message.get("License-Expression")
                or message.get("License")
                or "not-declared",
                "license_classifiers": [
                    value
                    for value in message.get_all("Classifier", [])
                    if value.startswith("License ::")
                ],
            }
        )
    output.write_text(
        json.dumps(
            {"schema_version": 1, "packages": packages},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (wheelhouse / "WHEELHOUSE-BUILD.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_repository_label": source_repository_label,
                "python_version": platform.python_version(),
                "platform": "ubuntu-22.04-amd64-cp310",
                "accepted_manylinux_tags": [
                    "manylinux_2_28_x86_64",
                    "manylinux_2_17_x86_64",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
