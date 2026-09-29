"""Compatibility entry point for the catalog and seasonal score refresh."""

from scripts.sync_catalog import main


if __name__ == "__main__":
    raise SystemExit(main(["--scores"]))
