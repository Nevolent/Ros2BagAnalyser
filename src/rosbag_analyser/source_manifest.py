from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Sequence


class ManifestError(RuntimeError):
    """A bounded source-inventory failure safe for operator output."""


MAX_MANIFEST_DEPTH = 64
MAX_MANIFEST_ENTRIES = 2_000_000


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    kind: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class ManifestResult:
    entry_count: int
    digest_sha256: str


def build_source_manifest(
    source_root: Path,
    *,
    max_depth: int,
    max_entries: int,
) -> tuple[ManifestEntry, ...]:
    if (
        max_depth <= 0
        or max_depth > MAX_MANIFEST_DEPTH
        or max_entries <= 0
        or max_entries > MAX_MANIFEST_ENTRIES
    ):
        raise ManifestError("Manifest bounds must be positive and explicit.")
    _reject_symlink_parent(source_root.absolute())
    try:
        root = source_root.resolve(strict=True)
        root_details = root.stat(follow_symlinks=False)
    except OSError as error:
        raise ManifestError("The approved source root is unavailable.") from error
    if not stat.S_ISDIR(root_details.st_mode) or source_root.is_symlink():
        raise ManifestError("The approved source root is not a safe directory.")

    collected: list[ManifestEntry] = []
    pending: list[tuple[Path, PurePosixPath, int]] = [(root, PurePosixPath(), 0)]
    while pending:
        directory, relative_directory, depth = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                children = []
                for child in iterator:
                    if len(collected) + len(children) >= max_entries:
                        raise ManifestError(
                            "The source manifest entry bound was exceeded."
                        )
                    children.append(child)
                children.sort(key=lambda item: item.name)
        except OSError as error:
            raise ManifestError("A source directory could not be inventoried.") from error
        if children and depth >= max_depth:
            raise ManifestError("The source manifest depth bound was exceeded.")
        directories: list[tuple[Path, PurePosixPath, int]] = []
        for child in children:
            try:
                details = child.stat(follow_symlinks=False)
            except OSError as error:
                raise ManifestError("A source entry could not be inventoried.") from error
            relative = relative_directory / child.name
            if child.is_symlink():
                kind = "symlink"
            elif stat.S_ISDIR(details.st_mode):
                kind = "directory"
                directories.append((Path(child.path), relative, depth + 1))
            elif stat.S_ISREG(details.st_mode):
                kind = "file"
            else:
                kind = "other"
            collected.append(
                ManifestEntry(
                    relative.as_posix(),
                    kind,
                    int(details.st_size),
                    int(details.st_mtime_ns),
                )
            )
        pending.extend(reversed(directories))
    return tuple(sorted(collected, key=lambda item: item.relative_path))


def write_source_manifest(
    source_root: Path,
    output_path: Path,
    *,
    max_depth: int,
    max_entries: int,
) -> ManifestResult:
    if output_path.exists() or output_path.is_symlink():
        raise ManifestError("Source manifest evidence already exists.")
    source = source_root.resolve(strict=True)
    output_absolute = output_path.absolute()
    temporary_path: Path | None = None
    try:
        output_absolute.relative_to(source)
    except ValueError:
        pass
    else:
        raise ManifestError("Source manifest evidence must be written outside source.")
    _reject_symlink_parent(output_absolute.parent)
    entries = build_source_manifest(
        source,
        max_depth=max_depth,
        max_entries=max_entries,
    )
    serialized_entries = [asdict(entry) for entry in entries]
    digest_payload = json.dumps(
        serialized_entries,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(digest_payload).hexdigest()
    document = {
        "schema_version": 1,
        "entry_count": len(entries),
        "digest_sha256": digest,
        "entries": serialized_entries,
    }
    try:
        output_absolute.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_absolute.parent,
            prefix=f".{output_absolute.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, sort_keys=True, separators=(",", ":"))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, output_absolute)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise ManifestError("Source manifest evidence could not be written.") from error
    return ManifestResult(len(entries), digest)


def _reject_symlink_parent(path: Path) -> None:
    existing: list[Path] = []
    current = path
    while not current.exists():
        existing.append(current)
        if current == current.parent:
            break
        current = current.parent
    try:
        if current.is_symlink():
            raise ManifestError("The evidence path contains a symbolic link.")
        resolved = current.resolve(strict=True)
        if resolved != current:
            raise ManifestError("The evidence path contains a symbolic link.")
    except OSError as error:
        raise ManifestError("The evidence path could not be validated.") from error
    del existing


def main(arguments: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Capture a bounded metadata-only inventory of an approved source root."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-depth", required=True, type=int)
    parser.add_argument("--max-entries", required=True, type=int)
    parsed = parser.parse_args(arguments)
    try:
        result = write_source_manifest(
            parsed.source_root,
            parsed.output,
            max_depth=parsed.max_depth,
            max_entries=parsed.max_entries,
        )
    except (ManifestError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(
        f"Source manifest captured: {result.entry_count} entries, "
        f"digest {result.digest_sha256}"
    )


if __name__ == "__main__":
    main()


__all__ = [
    "ManifestEntry",
    "ManifestError",
    "ManifestResult",
    "build_source_manifest",
    "write_source_manifest",
]
