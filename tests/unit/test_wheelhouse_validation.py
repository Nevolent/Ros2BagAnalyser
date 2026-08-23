from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[2] / "deploy" / "scripts" / "validate_wheelhouse.py"
)
SPEC = importlib.util.spec_from_file_location("validate_wheelhouse", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
wheelhouse_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wheelhouse_validation)


def create_wheelhouse(path: Path) -> None:
    path.mkdir()
    wheel = path / "package-1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (path / "SHA256SUMS").write_text(
        f"{digest}  {wheel.name}\n", encoding="ascii"
    )


def test_exact_checksummed_wheelhouse_is_accepted(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    create_wheelhouse(wheelhouse)

    wheelhouse_validation.validate_wheelhouse(wheelhouse)


def test_unlisted_extra_or_symlink_is_rejected(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    create_wheelhouse(wheelhouse)
    (wheelhouse / "unlisted.whl").write_bytes(b"unlisted")

    with pytest.raises(SystemExit, match="invalid"):
        wheelhouse_validation.validate_wheelhouse(wheelhouse)

    (wheelhouse / "unlisted.whl").unlink()
    (wheelhouse / "alias.whl").symlink_to("package-1.0-py3-none-any.whl")
    with pytest.raises(SystemExit, match="invalid"):
        wheelhouse_validation.validate_wheelhouse(wheelhouse)
