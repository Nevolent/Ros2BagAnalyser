from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile

import pytest


MODULE_PATH = (
    Path(__file__).parents[2]
    / "deploy"
    / "scripts"
    / "validate_release_archive.py"
)
SPEC = importlib.util.spec_from_file_location("validate_release_archive", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_archive)


def write_archive(path: Path, members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for info, content in members:
            archive.addfile(info, io.BytesIO(content) if info.isfile() else None)


def regular(name: str, content: bytes = b"content") -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    return info, content


def test_release_archive_accepts_only_regular_release_tree(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    write_archive(archive, [regular("release/release-manifest.json")])

    release_archive.validate_archive(str(archive))


@pytest.mark.parametrize("unsafe_name", ["../escape", "/absolute", "other/file"])
def test_release_archive_rejects_unsafe_paths(
    tmp_path: Path, unsafe_name: str
) -> None:
    archive = tmp_path / "release.tar.gz"
    write_archive(archive, [regular(unsafe_name)])

    with pytest.raises(SystemExit, match="unsafe"):
        release_archive.validate_archive(str(archive))


def test_release_archive_rejects_links(tmp_path: Path) -> None:
    archive = tmp_path / "release.tar.gz"
    link = tarfile.TarInfo("release/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc"
    write_archive(archive, [(link, b"")])

    with pytest.raises(SystemExit, match="unsafe"):
        release_archive.validate_archive(str(archive))


def test_installed_dependency_identity_is_readable_with_private_builder_permissions(tmp_path: Path) -> None:
    release = tmp_path / 'release'
    scripts = release / 'deploy/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'run-service').write_text('#!/bin/sh\n')
    wheelhouse = release / 'wheelhouse'
    wheelhouse.mkdir()
    checksum = wheelhouse / 'SHA256SUMS'
    content = b'synthetic dependency identity\n'
    checksum.write_bytes(content)
    checksum.chmod(0o600)
    private = tmp_path / 'recovery.env'
    private.write_text('synthetic private fixture')
    private.chmod(0o600)
    installer = (MODULE_PATH.parent / 'install-release').read_text()
    permissions = installer.split('find "$staging/release/deploy/scripts"', 1)[1].split('\nmv --', 1)[0]
    # Exercise the installer's publication permissions without root installation,
    # downloads or pip. Fixture ownership already matches this test's user.
    permissions = ('find "$staging/release/deploy/scripts"' + permissions).replace(
        'chown -R root:root "$staging/release"', '')
    subprocess.run(['bash', '-eu', '-c', permissions], check=True,
                   env=dict(os.environ, staging=str(tmp_path)), capture_output=True)
    assert checksum.stat().st_mode & 0o777 == 0o644
    assert checksum.read_bytes() == content
    assert scripts.stat().st_mode & 0o777 == 0o755
    assert (scripts / 'run-service').stat().st_mode & 0o777 == 0o755
    assert private.stat().st_mode & 0o777 == 0o600
