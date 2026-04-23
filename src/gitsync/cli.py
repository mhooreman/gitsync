"""Provide the gitsync command line interface."""

import pathlib

import click

from ._core import Synchonizer


@click.command(name="gitsync")
@click.argument(
    "vanilla_dir", required=True, type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True,
        allow_dash=False, path_type=pathlib.Path
    )
)
@click.argument(
    "repository_dir", required=True, type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True,
        writable=True, allow_dash=False, path_type=pathlib.Path
    )
)
def main(vanilla_dir: pathlib.Path, repository_dir: pathlib.Path) -> None:
    """Synchronize a vanilla directory to a git repository."""
    Synchonizer(vanilla_dir=vanilla_dir, repository_dir=repository_dir)()


if __name__ == "__main__":
    main()
