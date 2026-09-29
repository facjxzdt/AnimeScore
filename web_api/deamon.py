"""Compatibility hook for existing external score-update schedulers."""

from scripts.sync_catalog import main


def updata_score():
    return main(["--scores"])
