from __future__ import annotations


RESERVED_CACHE_DIRECTORY_NAME = "Rosbag_Analyser_Cache"
_RESERVED_CACHE_DIRECTORY_CASEFOLD = RESERVED_CACHE_DIRECTORY_NAME.casefold()


def is_reserved_cache_root_entry(name: str) -> bool:
    """Return whether an archive-root entry belongs to analyser-owned storage."""

    return name.casefold() == _RESERVED_CACHE_DIRECTORY_CASEFOLD


__all__ = ["RESERVED_CACHE_DIRECTORY_NAME", "is_reserved_cache_root_entry"]
