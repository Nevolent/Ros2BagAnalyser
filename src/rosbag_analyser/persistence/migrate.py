from __future__ import annotations

from rosbag_analyser.config import ConfigurationError, database_url_from_environment

from .database import CatalogSchemaError, apply_catalog_migration


def main() -> None:
    try:
        database_url = database_url_from_environment()
        apply_catalog_migration(database_url)
    except (ConfigurationError, CatalogSchemaError) as error:
        raise SystemExit(str(error)) from error
    print("Catalog migration applied.")


if __name__ == "__main__":
    main()
