from __future__ import annotations


POSTGRES_INTEGER_MIN = -2_147_483_648
POSTGRES_INTEGER_MAX = 2_147_483_647
POSTGRES_BIGINT_MIN = -9_223_372_036_854_775_808
POSTGRES_BIGINT_MAX = 9_223_372_036_854_775_807


def is_postgres_integer(value: int) -> bool:
    return POSTGRES_INTEGER_MIN <= value <= POSTGRES_INTEGER_MAX


def is_postgres_bigint(value: int) -> bool:
    return POSTGRES_BIGINT_MIN <= value <= POSTGRES_BIGINT_MAX


def is_postgres_text(value: str) -> bool:
    if "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
